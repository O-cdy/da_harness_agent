from collections.abc import Mapping
from pathlib import Path

import pytest

from harness.core.memory import MemoryError, assemble
from harness.core.orchestrator import OrchestratorError, run_playbook
from harness.core.policy import Policy, PolicyError
from harness.execution.reader import SqlGuardError, assert_read_only_grants, run_read_only
from harness.execution.sql_guard import guard_sql
from harness.runtime import review_statement

ROOT = Path(__file__).resolve().parents[2]
ORDERS = "orders"


class _Session:
    def __init__(self, grants: list[str]) -> None:
        self.grants = grants
        self.statements: list[str] = []
        self.closed = False

    def execute(self, statement: str) -> list[tuple[object, ...]]:
        self.statements.append(statement)
        if statement.startswith("SHOW GRANTS"):
            return [(grant,) for grant in self.grants]
        return [("ok",)]

    def close(self) -> None:
        self.closed = True


def test_prior_fingerprint_is_kept_and_metric_values_are_rejected(tmp_path) -> None:
    errors = tmp_path / "errors" / "index.md"
    errors.parent.mkdir()
    errors.write_text("index", encoding="utf-8")
    kept = assemble(
        caliber_paths=[],
        errors_index=errors,
        previous_evidence={"fingerprint": "sha256:prior", "note": "narrative only"},
    )
    assert kept["previous_fingerprint"] == "sha256:prior"
    assert kept["previous_metric_values"] == {}
    with pytest.raises(MemoryError, match="previous metric"):
        assemble(
            caliber_paths=[],
            errors_index=errors,
            previous_evidence={"fingerprint": "sha256:prior", "M101": "10"},
        )
    with pytest.raises(MemoryError, match="previous metric"):
        assemble(
            caliber_paths=[],
            errors_index=errors,
            previous_evidence={"fingerprint": "sha256:prior", "notes": [1.5]},
        )
    with pytest.raises(MemoryError, match="content hash"):
        assemble(
            caliber_paths=[],
            errors_index=errors,
            previous_evidence={"fingerprint": "not-a-hash"},
        )


def test_sql_is_reviewed_and_not_executed_before_c2(tmp_path) -> None:
    calls: list[dict[str, object]] = []

    def execute(statement: dict[str, object]) -> dict[str, object]:
        calls.append(statement)
        return {"executed": True}

    with pytest.raises(SqlGuardError, match="write"):
        run_playbook(
            ROOT,
            "tests/fixtures/playbooks/echo.yaml",
            ["shopify"],
            statements=["DELETE FROM orders"],
            review_sql=lambda sql: review_statement(sql, playbook=False, allowed_objects={ORDERS}),
            execute_sql=execute,
            evidence_dir=tmp_path / "sql",
        )
    assert calls == []
    assert not (tmp_path / "sql").exists()


def test_read_only_session_rejects_missing_login_and_write_grants() -> None:
    opened: list[str] = []

    def connect(_env: Mapping[str, str]) -> _Session:
        opened.append("open")
        return _Session(["GRANT SELECT ON demo.* TO 'reader'@'%'"])

    with pytest.raises(SqlGuardError, match="credentials"):
        run_read_only(
            {},
            "SELECT 1 FROM orders LIMIT 1",
            playbook=False,
            allowed_objects={ORDERS},
            connect=connect,
        )
    assert opened == []

    session = _Session(["GRANT SELECT ON demo.* TO 'reader'@'%'"])
    result = run_read_only(
        {"MYSQL_HOST": "127.0.0.1", "MYSQL_USER": "reader", "MYSQL_PASSWORD": "placeholder"},
        "SELECT item_gross_amount FROM orders WHERE order_created_date >= '2026-01-01' LIMIT 1",
        playbook=True,
        allowed_objects={ORDERS},
        connect=lambda _env: session,
    )
    assert result["executed"] is True
    assert session.closed is True
    assert session.statements[0] == "SET SESSION TRANSACTION READ ONLY"
    assert "2026-01-01" not in str(result["sql"])
    assert all(not text.startswith(("INSERT", "UPDATE", "DELETE")) for text in session.statements)
    with pytest.raises(SqlGuardError, match="missing"):
        assert_read_only_grants([])
    with pytest.raises(SqlGuardError, match="writes"):
        assert_read_only_grants(["GRANT SELECT, INSERT ON demo.* TO 'reader'@'%'"])
    with pytest.raises(SqlGuardError, match="write"):
        guard_sql(
            "UPDATE orders SET item_gross_amount = 1", playbook=False, allowed_objects={ORDERS}
        )


def test_policy_hook_runs_before_and_blocks_network() -> None:
    policy = Policy(allowlist=set())
    calls: list[str] = []
    with pytest.raises(PolicyError, match="network denied"):
        policy.around(
            {"capability": "llm", "network": True, "classification": "restricted"},
            lambda: calls.append("ran"),
        )
    assert calls == []


def test_valid_sql_stays_archived_until_c2(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def execute(statement: dict[str, object]) -> dict[str, object]:
        calls.append(statement)
        return {"executed": True}

    result = run_playbook(
        ROOT,
        "tests/fixtures/playbooks/echo.yaml",
        ["shopify"],
        statements=["SELECT 1 FROM orders LIMIT 1"],
        review_sql=lambda sql: review_statement(sql, playbook=False, allowed_objects={ORDERS}),
        execute_sql=execute,
        evidence_dir=tmp_path / "held",
    )
    assert calls == []
    archived = result["sql_archive"][0]
    assert archived["executed"] is False
    assert archived["reason"] == "c2 placeholder is not approval"
    assert "SELECT" in str(archived["sql"])


def test_sql_without_a_reviewer_is_rejected() -> None:
    with pytest.raises(OrchestratorError, match="review"):
        run_playbook(
            ROOT,
            "tests/fixtures/playbooks/echo.yaml",
            ["shopify"],
            statements=["SELECT 1 FROM orders LIMIT 1"],
        )


def test_approved_sql_executes_the_reviewed_statement(tmp_path: Path) -> None:
    calls: list[dict[str, object]] = []

    def execute(statement: dict[str, object]) -> dict[str, object]:
        calls.append(statement)
        return {"executed": True, "sql": statement["sql"]}

    result = run_playbook(
        ROOT,
        "tests/fixtures/playbooks/echo.yaml",
        ["shopify"],
        statements=["SELECT 1 FROM orders LIMIT 1"],
        review_sql=lambda sql: review_statement(sql, playbook=False, allowed_objects={ORDERS}),
        execute_sql=execute,
        c2_approved=True,
        evidence_dir=tmp_path / "approved",
    )
    assert len(calls) == 1
    assert "SELECT" in str(calls[0]["sql"])
    assert result["sql_archive"] == [{"executed": True, "sql": calls[0]["sql"]}]


def test_approved_sql_still_requires_an_executor() -> None:
    with pytest.raises(OrchestratorError, match="executor"):
        run_playbook(
            ROOT,
            "tests/fixtures/playbooks/echo.yaml",
            ["shopify"],
            statements=["SELECT 1 FROM orders LIMIT 1"],
            review_sql=lambda sql: review_statement(sql, playbook=False, allowed_objects={ORDERS}),
            c2_approved=True,
        )
