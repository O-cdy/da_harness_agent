"""Catalog-only source contract. Business tables are not queried."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml

from harness.execution.reader import QuerySession
from harness.execution.sql_guard import SqlGuardError, assert_credentials

_IDENT = re.compile(r"\A[\w]+\Z", re.UNICODE)


class SourceContractError(ValueError):
    """A profile does not name the schemas or platform being checked."""


def expected_from_profile(
    profile: Mapping[str, Any],
    platform_ids: list[str],
) -> list[dict[str, Any]]:
    """Read schema names and whitelist tables from a profile object."""
    datasource = profile.get("datasource")
    if not isinstance(datasource, Mapping):
        raise SourceContractError("profile datasource is absent")
    schemas = [datasource.get("facts_schema"), datasource.get("dims_schema")]
    if any(not isinstance(item, str) or not item for item in schemas):
        raise SourceContractError("profile schemas are absent")
    platforms = datasource.get("platforms")
    if not isinstance(platforms, Mapping):
        raise SourceContractError("profile platforms are absent")
    expected: list[dict[str, Any]] = []
    for platform_id in platform_ids:
        spec = platforms.get(platform_id)
        if not isinstance(spec, Mapping):
            raise SourceContractError("platform is absent")
        whitelist = spec.get("whitelist")
        if not isinstance(whitelist, list) or not whitelist:
            raise SourceContractError("platform whitelist is absent")
        declared = spec.get("required_columns") or {}
        if not isinstance(declared, Mapping):
            raise SourceContractError("required columns are not a mapping")
        for table in whitelist:
            columns = declared.get(table, [])
            if not isinstance(columns, list):
                raise SourceContractError("required columns are not a list")
            expected.append(
                {
                    "adapter_id": str(spec.get("adapter_id") or platform_id),
                    "contract_version": str(spec.get("adapter_contract_version") or "1"),
                    "platform_id": platform_id,
                    "table": str(table),
                    "schemas": [str(item) for item in schemas],
                    "required_columns": [str(column) for column in columns],
                }
            )
    return expected


def collect_source_contract(
    env: Mapping[str, str],
    profile: Mapping[str, Any],
    platform_ids: list[str],
    *,
    connect: Callable[[Mapping[str, str]], QuerySession],
) -> list[dict[str, Any]]:
    """Read information_schema for the declared tables. Missing login does not connect."""
    assert_credentials(env)
    expected = expected_from_profile(profile, platform_ids)
    if not expected:
        return []
    session = connect(dict(env))
    try:
        rows = session.execute(catalog_sql(expected))
    finally:
        session.close()
    return assemble_contracts(expected, rows)


def catalog_sql(expected: list[dict[str, Any]]) -> str:
    """Build one catalog query. Identifiers are quoted only after validation."""
    schemas = sorted({schema for item in expected for schema in item["schemas"]})
    tables = sorted({str(item["table"]) for item in expected})
    schema_sql = ", ".join(_literal(schema) for schema in schemas)
    table_sql = ", ".join(_literal(table) for table in tables)
    return (
        "SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE "  # noqa: S608
        "FROM information_schema.COLUMNS "
        f"WHERE TABLE_SCHEMA IN ({schema_sql}) AND TABLE_NAME IN ({table_sql})"
    )


def assemble_contracts(
    expected: list[dict[str, Any]],
    rows: list[tuple[object, ...]],
) -> list[dict[str, Any]]:
    """Compare catalog rows with the declaration. No business row is accepted."""
    found: dict[str, dict[str, set[str]]] = {}
    observed: list[tuple[str, str, str, str]] = []
    for row in rows:
        parsed = _parsed_row(row)
        if parsed is None:
            continue
        schema, table, column, data_type = parsed
        found.setdefault(table, {}).setdefault(schema, set()).add(column)
        observed.append((schema, table, column, data_type))
    by_adapter: dict[str, list[dict[str, Any]]] = {}
    versions: dict[str, str] = {}
    for item in expected:
        by_adapter.setdefault(str(item["adapter_id"]), []).append(item)
        versions[str(item["adapter_id"])] = str(item["contract_version"])
    contracts: list[dict[str, Any]] = []
    for adapter_id, items in by_adapter.items():
        unmapped: list[str] = []
        ready = True
        tables = {str(item["table"]) for item in items}
        for item in items:
            table = str(item["table"])
            locations = [schema for schema in item["schemas"] if schema in found.get(table, {})]
            if len(locations) != 1:
                ready = False
                unmapped.append(table)
                continue
            columns = found[table][locations[0]]
            for column in item["required_columns"]:
                if column not in columns:
                    ready = False
                    unmapped.append(f"{table}.{column}")
        adapter_rows = sorted(row for row in observed if row[1] in tables)
        contracts.append(
            {
                "adapter_id": adapter_id,
                "contract_version": versions[adapter_id],
                "schema_fingerprint": _digest(adapter_rows),
                "capability": {"tables": "ready" if ready else "missing"},
                "unmapped_fields": unmapped,
                "watermark": None,
                "row_count": None,
                "business_rows_read": 0,
                "quality_assertions": [
                    {
                        "assertion_id": "no-business-rows",
                        "passed": True,
                        "summary": "business rows were not read",
                    }
                ],
            }
        )
    return contracts


def write_evidence(directory: Path, contracts: list[dict[str, Any]], sql: str) -> None:
    """Store hashes and the catalog statement. Credentials are not accepted here."""
    directory.mkdir(parents=True, exist_ok=True)
    safe = [
        {
            "adapter_id": item["adapter_id"],
            "schema_fingerprint": item["schema_fingerprint"],
            "capability": item["capability"],
            "unmapped_count": len(item["unmapped_fields"]),
            "watermark": None,
            "row_count": None,
            "business_rows_read": 0,
        }
        for item in contracts
    ]
    encoded = json.dumps(safe, sort_keys=True).encode()
    (directory / "catalog.sql").write_text(sql + "\n", encoding="utf-8")
    (directory / "result.json").write_text(
        json.dumps(safe, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    (directory / "source_manifest.json").write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "logical_id": "information-schema",
                        "row_count": 0,
                        "business_rows_read": 0,
                        "query_hash": "sha256:" + hashlib.sha256(sql.encode()).hexdigest(),
                        "snapshot_hash": "sha256:" + hashlib.sha256(encoded).hexdigest(),
                    }
                ]
            },
            sort_keys=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    (directory / "params.json").write_text(
        json.dumps({"python": "3.13", "driver": "pymysql", "model": "none"}, sort_keys=True),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    """Run one local catalog probe. Automated tests must not call this."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--platform", action="append", required=True)
    parser.add_argument("--evidence-dir", required=True)
    args = parser.parse_args(argv)
    from harness.execution.live_probe import connect_mysql, load_env_file

    env = load_env_file(Path(args.env_file))
    loaded = yaml.safe_load(Path(args.profile).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise SourceContractError("profile datasource is absent")
    profile: dict[str, Any] = loaded
    expected = expected_from_profile(profile, list(args.platform))
    try:
        contracts = collect_source_contract(
            env,
            profile,
            list(args.platform),
            connect=connect_mysql,
        )
    except SqlGuardError:
        print(json.dumps({"business_rows_read": 0, "connected": False}))
        return 1
    except Exception as error:
        errno = error.args[0] if error.args and isinstance(error.args[0], int) else None
        print(json.dumps({"business_rows_read": 0, "connected": False, "errno": errno}))
        return 1
    write_evidence(Path(args.evidence_dir), contracts, catalog_sql(expected))
    print(json.dumps(_public_summary(contracts), sort_keys=True))
    return 0


def _public_summary(contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "adapter_id": item["adapter_id"],
            "schema_fingerprint": item["schema_fingerprint"],
            "capability": item["capability"],
            "unmapped_count": len(item["unmapped_fields"]),
            "business_rows_read": item["business_rows_read"],
            "watermark": item["watermark"],
        }
        for item in contracts
    ]


def _literal(identifier: str) -> str:
    if _IDENT.fullmatch(identifier) is None:
        raise SqlGuardError("identifier rejected")
    return "'" + identifier.replace("'", "''") + "'"


def _parsed_row(row: tuple[object, ...]) -> tuple[str, str, str, str] | None:
    if len(row) < 4 or any(item is None for item in row[:4]):
        return None
    return (str(row[0]), str(row[1]), str(row[2]), str(row[3]))


def _digest(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
