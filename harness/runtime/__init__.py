"""Composition root. Core reaches SQL and adapters only through callables built here."""

from harness.execution.sql_guard import guard_sql


def review_statement(
    sql: str,
    *,
    playbook: bool,
    allowed_objects: set[str],
) -> dict[str, object]:
    """Parse and parameterize one statement. This does not open a connection."""
    return guard_sql(sql, playbook=playbook, allowed_objects=allowed_objects)
