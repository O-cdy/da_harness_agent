import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from harness.core.memory import MemoryError, assemble
from harness.core.orchestrator import OrchestratorError, run_playbook
from harness.core.policy import Policy, PolicyError
from harness.execution.reader import (
    SqlGuardError,
    assert_read_only_grants,
    prove_zero_write,
    run_read_only,
)
from harness.execution.source_contract import (
    catalog_sql,
    collect_source_contract,
    expected_from_profile,
    write_evidence,
)
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


def test_zero_write_probe_keeps_grant_text_out_of_the_result() -> None:
    class _Probe:
        def __init__(self, grants: list[str], *, accept: bool = False) -> None:
            self.grants = grants
            self.accept = accept
            self.statements: list[str] = []
            self.closed = False

        def execute(self, statement: str) -> list[tuple[object, ...]]:
            self.statements.append(statement)
            if statement.startswith("SELECT @@SESSION"):
                return [(1,)]
            if statement.startswith("SHOW GRANTS"):
                return [(grant,) for grant in self.grants]
            if statement.startswith("INSERT") and not self.accept:
                raise RuntimeError(1792, "server detail hidden")
            if statement.startswith("CREATE TEMPORARY") and not self.accept:
                raise RuntimeError(1792, "server detail hidden")
            return []

        def close(self) -> None:
            self.closed = True

    login = {"MYSQL_HOST": "127.0.0.1", "MYSQL_USER": "reader", "MYSQL_PASSWORD": "placeholder"}
    session = _Probe(["GRANT SELECT ON demo.* TO 'reader'@'%'"])
    result = prove_zero_write(login, connect=lambda _env: session)
    encoded = json.dumps(result)
    assert result["three_layers_hold"] is True
    assert result["business_rows_read"] == 0
    assert "ROLLBACK" in session.statements
    assert session.closed is True
    assert "reader" not in encoded
    assert "demo" not in encoded
    writer = _Probe(["GRANT SELECT, INSERT ON demo.* TO 'writer'@'%'"])
    denied = prove_zero_write(login, connect=lambda _env: writer)
    assert denied["three_layers_hold"] is False
    assert denied["read_only_account"] is False
    assert denied["write_verbs"] == ["INSERT"]
    assert "writer" not in json.dumps(denied)
    inconclusive = _Probe(["GRANT SELECT ON demo.* TO 'reader'@'%'"])

    def _execute(statement: str) -> list[tuple[object, ...]]:
        inconclusive.statements.append(statement)
        if statement.startswith("SELECT @@SESSION"):
            return [(1,)]
        if statement.startswith("SHOW GRANTS"):
            return [(grant,) for grant in inconclusive.grants]
        if statement.startswith("INSERT"):
            raise RuntimeError(1046, "hidden")
        if statement.startswith("SHOW DATABASES"):
            return [("appdb",)]
        if statement.startswith("USE"):
            return []
        if statement.startswith("CREATE TEMPORARY"):
            raise RuntimeError(1792, "hidden")
        return []

    inconclusive.execute = _execute  # type: ignore[method-assign]
    recovered = prove_zero_write(login, connect=lambda _env: inconclusive)
    assert recovered["write_errno"] == 1792
    assert recovered["session_blocked_write"] is True
    assert recovered["write_accepted"] is False
    assert "appdb" not in json.dumps(recovered)


def test_source_contract_reports_catalog_gaps_without_business_rows(tmp_path: Path) -> None:
    profile = {
        "datasource": {
            "facts_schema": "facts",
            "dims_schema": "dims",
            "platforms": {
                "shopify": {
                    "adapter_id": "shopify",
                    "adapter_contract_version": "1",
                    "whitelist": ["orders", "refunds"],
                    "required_columns": {"orders": ["order_created_date"]},
                }
            },
        }
    }
    opened: list[str] = []

    def connect(_env: Mapping[str, str]) -> object:
        opened.append("open")
        raise AssertionError("connect must not run without credentials")

    with pytest.raises(SqlGuardError, match="credentials"):
        collect_source_contract({}, profile, ["shopify"], connect=connect)  # type: ignore[arg-type]
    assert opened == []

    class _Catalog:
        def __init__(self) -> None:
            self.sql = ""
            self.closed = False

        def execute(self, statement: str) -> list[tuple[object, ...]]:
            self.sql = statement
            return [("facts", "orders", "id", "bigint")]

        def close(self) -> None:
            self.closed = True

    session = _Catalog()
    login = {"MYSQL_HOST": "127.0.0.1", "MYSQL_USER": "reader", "MYSQL_PASSWORD": "placeholder"}
    contracts = collect_source_contract(
        login,
        profile,
        ["shopify"],
        connect=lambda _env: session,
    )
    assert session.closed is True
    assert "information_schema.COLUMNS" in session.sql
    assert "FROM `orders`" not in session.sql
    assert contracts[0]["business_rows_read"] == 0
    assert contracts[0]["watermark"] is None
    assert contracts[0]["row_count"] is None
    assert contracts[0]["capability"] == {"tables": "missing"}
    assert contracts[0]["unmapped_fields"] == ["orders.order_created_date", "refunds"]
    assert str(contracts[0]["schema_fingerprint"]).startswith("sha256:")
    assert "buyer@example.com" not in json.dumps(contracts)

    ambiguous = _Catalog()
    ambiguous.execute = lambda _statement: [  # type: ignore[method-assign]
        ("facts", "orders", "id", "bigint"),
        ("dims", "orders", "id", "bigint"),
    ]
    both = collect_source_contract(login, profile, ["shopify"], connect=lambda _env: ambiguous)
    assert both[0]["unmapped_fields"][0] == "orders"
    assert both[0]["capability"] == {"tables": "missing"}

    opened.clear()

    def refuse(_env: Mapping[str, str]) -> object:
        opened.append("open")
        raise AssertionError("empty declaration must not connect")

    assert collect_source_contract(login, profile, [], connect=refuse) == []  # type: ignore[arg-type]
    assert opened == []
    with pytest.raises(SqlGuardError, match="identifier"):
        catalog_sql([{"table": "orders;drop", "schemas": ["facts"]}])
    assert "'维表'" in catalog_sql([{"table": "维表", "schemas": ["facts"]}])
    evidence = tmp_path / "catalog"
    write_evidence(evidence, contracts, session.sql)
    saved = json.loads((evidence / "result.json").read_text(encoding="utf-8"))
    assert saved[0]["business_rows_read"] == 0
    assert saved[0]["row_count"] is None
    assert "MYSQL_PASSWORD" not in (evidence / "source_manifest.json").read_text(encoding="utf-8")


def test_orchestrator_keeps_injected_source_contract_read_only(tmp_path: Path) -> None:
    seen: list[int] = []

    def contract() -> list[dict[str, object]]:
        seen.append(1)
        return [
            {
                "adapter_id": "shopify",
                "schema_fingerprint": "sha256:abc",
                "capability": {"tables": "ready"},
                "unmapped_fields": [],
                "watermark": None,
                "row_count": None,
                "business_rows_read": 0,
            }
        ]

    result = run_playbook(
        ROOT,
        "tests/fixtures/playbooks/echo.yaml",
        ["shopify"],
        source_contract=contract,
        evidence_dir=tmp_path / "contract",
    )
    assert seen == [1]
    assert result["source_contracts"][0]["schema_fingerprint"] == "sha256:abc"
    assert result["source_contracts"][0]["business_rows_read"] == 0
    with pytest.raises(OrchestratorError, match="business rows"):
        run_playbook(
            ROOT,
            "tests/fixtures/playbooks/echo.yaml",
            ["shopify"],
            source_contract=lambda: [{"business_rows_read": 2}],
        )
    assert (
        expected_from_profile(
            {
                "datasource": {
                    "facts_schema": "facts",
                    "dims_schema": "dims",
                    "platforms": {"shopify": {"adapter_id": "shopify", "whitelist": ["orders"]}},
                }
            },
            ["shopify"],
        )[0]["table"]
        == "orders"
    )
    sql = catalog_sql(
        [
            {
                "table": "orders",
                "schemas": ["facts", "dims"],
            }
        ]
    )
    assert "information_schema.COLUMNS" in sql


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
