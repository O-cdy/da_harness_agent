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

_WRITE_GRANT = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|ALL PRIVILEGES)\b",
    re.IGNORECASE,
)


class QuerySession(Protocol):
    def execute(self, statement: str) -> list[tuple[object, ...]]:
        """Run one driver statement and return its rows."""
        ...

    def close(self) -> None:
        """Release the session."""
        ...


def assert_read_only_grants(grants: list[str]) -> None:
    """Reject a login that can change data."""
    if not grants:
        raise SqlGuardError("database grant is missing")
    for grant in grants:
        if _WRITE_GRANT.search(grant):
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
