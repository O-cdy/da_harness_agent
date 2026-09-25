"""Read-only driver session. A missing login never opens a connection."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Protocol

from harness.execution.sql_guard import (
    SqlGuardError,
    assert_credentials,
    guard_sql,
    session_preamble,
)

_PROBE_WRITE = "INSERT INTO harness_ro_probe (id) VALUES (1)"
_SYSTEM_SCHEMAS = frozenset({"information_schema", "mysql", "performance_schema", "sys"})
_SESSION_BLOCKED = frozenset({1044, 1142, 1227, 1290, 1792})


class QuerySession(Protocol):
    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Run one driver statement and return its rows."""
        ...

    def close(self) -> None:
        """Release the session."""
        ...


def summarize_grants(grants: list[str]) -> dict[str, object]:
    """Classify privileges without returning the grant text."""
    verbs: set[str] = set()
    for grant in grants:
        for verb in ("INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "ALL PRIVILEGES"):
            if re.search(rf"\b{re.escape(verb)}\b", grant, re.IGNORECASE):
                verbs.add(verb)
    return {
        "grant_count": len(grants),
        "write_verbs": sorted(verbs),
        "read_only_account": bool(grants) and not verbs,
    }


def assert_read_only_grants(grants: list[str]) -> None:
    """Reject a login that can change data."""
    summary = summarize_grants(grants)
    if summary["grant_count"] == 0:
        raise SqlGuardError("database grant is missing")
    if not summary["read_only_account"]:
        raise SqlGuardError("database grant allows writes")


def run_read_only(
    env: Mapping[str, str],
    sql: str,
    *,
    playbook: bool,
    allowed_objects: set[str],
    connect: Callable[[Mapping[str, str]], QuerySession],
) -> dict[str, object]:
    """Guard the statement, then send only the parameterized text on a read-only session."""
    assert_credentials(env)
    guarded = guard_sql(sql, playbook=playbook, allowed_objects=allowed_objects)
    session = connect(dict(env))
    try:
        for statement in session_preamble():
            session.execute(statement)
        grant_rows = session.execute("SHOW GRANTS FOR CURRENT_USER")
        grants = [str(row[0]) for row in grant_rows if row]
        assert_read_only_grants(grants)
        session.execute(str(guarded["sql"]))
    finally:
        session.close()
    return {
        "executed": True,
        "sql": guarded["sql"],
        "bindings": guarded["bindings"],
        "session": guarded["session"],
    }


def prove_zero_write(
    env: Mapping[str, str],
    *,
    connect: Callable[[Mapping[str, str]], QuerySession],
) -> dict[str, object]:
    """Open one read-only session and record whether a write was accepted.

    The result never includes credentials, grant text, or query rows.
    """
    assert_credentials(env)
    ast_blocked = False
    try:
        guard_sql(
            "DELETE FROM harness_ro_probe",
            playbook=False,
            allowed_objects={"harness_ro_probe"},
        )
    except SqlGuardError as error:
        ast_blocked = "write" in str(error)
    session = connect(dict(env))
    write_accepted = False
    write_errno: int | None = None
    read_only_flag = 0
    summary: dict[str, object] = {
        "grant_count": 0,
        "write_verbs": [],
        "read_only_account": False,
    }
    statements = [
        "SET SESSION TRANSACTION READ ONLY",
        "SELECT @@SESSION.transaction_read_only",
        "START TRANSACTION",
        "SELECT @@SESSION.transaction_read_only",
        "SHOW GRANTS FOR CURRENT_USER",
        "INSERT INTO harness_ro_probe (id) VALUES (1)",
    ]
    try:
        for statement in session_preamble():
            session.execute(statement)
        before_rows = session.execute("SELECT @@SESSION.transaction_read_only")
        session.execute("START TRANSACTION")
        flag_rows = session.execute("SELECT @@SESSION.transaction_read_only")
        read_only_before = _flag(before_rows)
        read_only_flag = _flag(flag_rows)
        grant_rows = session.execute("SHOW GRANTS FOR CURRENT_USER")
        summary = summarize_grants([str(row[0]) for row in grant_rows if row])
        try:
            session.execute(_PROBE_WRITE)
            write_accepted = True
        except Exception as error:
            write_errno = _errno(error)
        if write_errno == 1046:
            statements.append("SHOW DATABASES")
            schema_rows = session.execute("SHOW DATABASES")
            schema = _schema_name(schema_rows)
            if schema is not None:
                statements.append("USE <schema>")
                session.execute(f"USE `{schema}`")
                statements.append("CREATE TEMPORARY TABLE harness_ro_probe (id INT)")
                try:
                    session.execute("CREATE TEMPORARY TABLE harness_ro_probe (id INT)")
                    write_accepted = True
                    write_errno = None
                    statements.append("DROP TEMPORARY TABLE harness_ro_probe")
                    session.execute("DROP TEMPORARY TABLE harness_ro_probe")
                except Exception as error:
                    write_accepted = False
                    write_errno = _errno(error)
        statements.append("ROLLBACK")
    finally:
        _rollback(session)
        session.close()
    session_blocked = (not write_accepted) and write_errno in _SESSION_BLOCKED
    return {
        "connected": True,
        "ast_blocks_write": ast_blocked,
        "session_read_only": read_only_flag == 1,
        "session_read_only_before_transaction": read_only_before == 1,
        "session_blocked_write": session_blocked,
        "write_accepted": write_accepted,
        "write_errno": write_errno,
        "business_rows_read": 0,
        "grant_count": summary["grant_count"],
        "write_verbs": summary["write_verbs"],
        "read_only_account": summary["read_only_account"],
        "statements": statements,
        "three_layers_hold": bool(
            ast_blocked and read_only_flag == 1 and session_blocked and summary["read_only_account"]
        ),
    }


def _schema_name(rows: list[tuple[object, ...]]) -> str | None:
    for row in rows:
        if not row:
            continue
        name = str(row[0])
        if name.lower() in _SYSTEM_SCHEMAS or re.fullmatch(r"[A-Za-z0-9_]+", name) is None:
            continue
        return name
    return None


def _flag(rows: list[tuple[object, ...]]) -> int:
    if not rows or not rows[0]:
        return 0
    raw_flag = rows[0][0]
    if isinstance(raw_flag, int) and not isinstance(raw_flag, bool):
        return raw_flag
    return 0


def _errno(error: BaseException) -> int | None:
    args = getattr(error, "args", ())
    if args and isinstance(args[0], int):
        return int(args[0])
    return None


def _rollback(session: QuerySession) -> None:
    try:
        session.execute("ROLLBACK")
    except Exception as error:
        _errno(error)
