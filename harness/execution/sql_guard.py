"""Read-only SQL guard. Statement shape is decided by the parser."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

import sqlglot
from sqlglot import exp

_WRITE = (exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command)
_SESSION = ("SET SESSION TRANSACTION READ ONLY",)


class SqlGuardError(ValueError):
    """A statement is not a single read-only, bounded query."""


def session_preamble() -> tuple[str, ...]:
    """Statements a driver must send before a read. This function does not connect."""
    return _SESSION


def assert_credentials(env: Mapping[str, str]) -> None:
    """Reject a missing database login before any connection is attempted."""
    if not env.get("MYSQL_HOST") or not env.get("MYSQL_USER") or not env.get("MYSQL_PASSWORD"):
        raise SqlGuardError("database credentials are absent")


def guard_sql(sql: str, *, playbook: bool, allowed_objects: set[str]) -> dict[str, object]:
    """Return a normalized statement plus hashed bindings, or reject it."""
    try:
        statements = sqlglot.parse(sql, read="mysql")
    except sqlglot.errors.ParseError as error:
        raise SqlGuardError("sql parse failed") from error
    if len(statements) != 1 or statements[0] is None:
        raise SqlGuardError("exactly one statement is allowed")
    statement = statements[0]
    if isinstance(statement, _WRITE) or statement.find(*_WRITE) is not None:
        raise SqlGuardError("write statement rejected")
    if isinstance(statement, exp.Use) or statement.find(exp.Use) is not None:
        raise SqlGuardError("dynamic schema selection rejected")
    objects = {table.sql(dialect="mysql") for table in statement.find_all(exp.Table)}
    if not objects or not objects <= allowed_objects:
        raise SqlGuardError("object is outside the allowlist")
    if playbook and statement.find(exp.Column) and not _has_time_window(statement):
        raise SqlGuardError("playbook sql requires a canonical time window")
    if not playbook and statement.find(exp.Limit) is None:
        raise SqlGuardError("ad-hoc sql requires a limit")
    bindings = [_binding(literal) for literal in statement.find_all(exp.Literal)]
    for literal in list(statement.find_all(exp.Literal)):
        literal.replace(exp.Placeholder())
    return {
        "sql": statement.sql(dialect="mysql"),
        "session": list(session_preamble()),
        "bindings": bindings,
    }


def _has_time_window(statement: exp.Expression) -> bool:
    return any(column.name == "order_created_date" for column in statement.find_all(exp.Column))


def _binding(literal: exp.Literal) -> dict[str, str]:
    raw = literal.this
    text = raw if isinstance(raw, str) else str(raw)
    digest = hashlib.sha256(text.encode()).hexdigest()
    kind = "number" if literal.is_number else "string"
    return {"type": kind, "hash": f"sha256:{digest}"}
