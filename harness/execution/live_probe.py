"""Manual read-only probe. Tests and CI must not import this module."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Mapping
from pathlib import Path

from harness.execution.reader import QuerySession, prove_zero_write
from harness.execution.sql_guard import SqlGuardError, session_preamble


class _Connection:
    def __init__(self, raw: object) -> None:
        self._raw = raw

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        cursor = self._raw.cursor()  # type: ignore[attr-defined]
        try:
            cursor.execute(statement)
            if cursor.description is None:
                return []
            rows = cursor.fetchall()
            return [tuple(row) for row in rows]
        finally:
            cursor.close()

    def close(self) -> None:
        self._raw.close()  # type: ignore[attr-defined]


def connect_mysql(env: Mapping[str, str]) -> QuerySession:
    """Open the env-configured server. Callers must not log the arguments."""
    import pymysql  # type: ignore[import-untyped]

    database = env.get("MYSQL_DATABASE") or None
    raw = pymysql.connect(
        host=env["MYSQL_HOST"],
        port=int(env.get("MYSQL_PORT") or "3306"),
        user=env["MYSQL_USER"],
        password=env["MYSQL_PASSWORD"],
        database=database,
        autocommit=False,
        connect_timeout=10,
        read_timeout=15,
        write_timeout=15,
        charset="utf8mb4",
        init_command=session_preamble()[0],
    )
    return _Connection(raw)


def load_env_file(path: Path) -> dict[str, str]:
    """Read KEY=VALUE lines. Missing keys stay absent."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def write_evidence(directory: Path, result: dict[str, object]) -> None:
    """Store the redacted probe. The directory is expected to be gitignored."""
    directory.mkdir(parents=True, exist_ok=True)
    recorded = result.get("statements")
    statements = [str(item) for item in recorded] if isinstance(recorded, list) else []
    sql_text = "\n".join(statements) + "\n"
    (directory / "probe.sql").write_text(sql_text, encoding="utf-8")
    safe = {key: value for key, value in result.items() if key not in {"write_verbs", "statements"}}
    verbs = result.get("write_verbs")
    safe["write_verbs"] = [str(item) for item in verbs] if isinstance(verbs, list) else []
    encoded = json.dumps(safe, sort_keys=True).encode()
    manifest = {
        "sources": [
            {
                "logical_id": "mysql-readonly-probe",
                "row_count": 0,
                "business_rows_read": 0,
                "query_hash": "sha256:" + hashlib.sha256(sql_text.encode()).hexdigest(),
                "snapshot_hash": "sha256:" + hashlib.sha256(encoded).hexdigest(),
            }
        ]
    }
    (directory / "source_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (directory / "result.json").write_text(
        json.dumps(safe, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (directory / "params.json").write_text(
        json.dumps(
            {"python": "3.13", "driver": "pymysql", "model": "none"},
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """Run the probe and print only the redacted result."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)
    env = load_env_file(Path(args.env_file))
    try:
        result = prove_zero_write(env, connect=connect_mysql)
    except SqlGuardError as error:
        result = {
            "connected": False,
            "three_layers_hold": False,
            "business_rows_read": 0,
            "reason": str(error),
        }
    except Exception as error:
        errno = error.args[0] if error.args and isinstance(error.args[0], int) else None
        result = {
            "connected": False,
            "three_layers_hold": False,
            "business_rows_read": 0,
            "errno": errno,
        }
    evidence = Path(args.evidence_dir)
    write_evidence(evidence, result)
    published = {key: value for key, value in result.items() if key != "statements"}
    print(json.dumps(published, sort_keys=True))
    return 0 if result.get("three_layers_hold") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
