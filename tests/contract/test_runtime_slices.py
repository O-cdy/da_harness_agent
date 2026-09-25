import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from harness.adapters.snapshot import (
    AdapterError,
    canonical_snapshot,
    read_delimited_file,
    require_credentials,
)
from harness.cli.app import app
from harness.core.contracts.models import ErrorEnvelope, NoOp
from harness.core.contracts.redaction import redact_text
from harness.core.noop import disabled
from harness.core.orchestrator import OrchestratorError, resume, run_playbook
from harness.core.policy import Policy, PolicyError
from harness.execution.sql_guard import SqlGuardError, assert_credentials, guard_sql
from harness.llm.port import LlmError, complete
from harness.metrics.registry import MetricError, compute, separate_state, unmapped_products
from harness.reporting.package import render, seal, validate
from harness.skills.scene import (
    SkillError,
    contribution,
    detect_anomalies,
    native_analysis,
    price_volume,
)

ROOT = Path(__file__).resolve().parents[2]
RUNNER = CliRunner()
ORDERS = "orders"


def test_echo_branches_pause_resume_and_cancel(tmp_path: Path) -> None:
    result = run_playbook(
        ROOT,
        "tests/fixtures/playbooks/echo.yaml",
        ["shopify"],
        evidence_dir=tmp_path / "evidence",
    )
    statuses = {branch["step_id"]: branch for branch in result["branches"]}
    assert statuses["align"]["status"] == "awaiting_alignment"
    assert "report_tier" not in statuses["align"]
    assert statuses["continue"]["report_tier"] == "dry_run"
    assert statuses["align"]["checkpoint"] != statuses["continue"]["checkpoint"]
    assert resume(str(statuses["align"]["checkpoint"]), "snapshotting") == "snapshotting"
    with pytest.raises(OrchestratorError, match="active"):
        resume("sha256:abc", "completed")
    assert result["phase_order"] == ["preflight", "plan", "sql", "snapshot"]
    assert result["sql_archive"] == [{"executed": False, "reason": "run has no statement"}]
    assert result["source_contracts"] == [
        {"business_rows_read": 0, "reason": "source contract is absent"}
    ]
    assert result["approvals"]["c3"]["status"] == "not_submitted"
    for name in ("plan.md", "trace.jsonl", "envelope.json", "checkpoint.json"):
        assert (tmp_path / "evidence" / name).is_file()
    events = [
        json.loads(line)
        for line in (tmp_path / "evidence" / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    required = {
        "schema_version",
        "event_id",
        "event_type",
        "run_id",
        "plan_revision",
        "step_id",
        "timestamp",
        "input_refs",
        "result_summary",
        "duration_ms",
        "classification",
    }
    assert events and required <= events[0].keys()
    assert {event["event_type"] for event in events} >= {"state", "policy", "approval", "artifact"}
    assert all("SELECT" not in str(event["result_summary"]) for event in events)
    with pytest.raises(OrchestratorError, match="checkpoint"):
        resume(None, "snapshotting")
    with pytest.raises(OrchestratorError, match="cancelled"):
        run_playbook(
            ROOT,
            "tests/fixtures/playbooks/echo.yaml",
            ["shopify"],
            evidence_dir=tmp_path / "cancelled",
            fail_closed=True,
        )
    assert not (tmp_path / "cancelled").exists()
    kept = tmp_path / "kept"
    kept.mkdir()
    (kept / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(OrchestratorError, match="cancelled"):
        run_playbook(
            ROOT,
            "tests/fixtures/playbooks/echo.yaml",
            ["shopify"],
            evidence_dir=kept,
            fail_closed=True,
        )
    assert (kept / "keep.txt").is_file()
    assert not (kept / "partial.tmp").exists()
    bare = run_playbook(ROOT, "tests/fixtures/playbooks/echo.yaml", ["shopify"])
    assert bare["playbook_id"] == "echo"
    broken = yaml.safe_load(
        (ROOT / "tests/fixtures/playbooks/echo.yaml").read_text(encoding="utf-8")
    )
    broken["steps"][0]["checkpoint"] = "bad"
    relative = Path("runs") / "broken-checkpoint.yaml"
    destination = ROOT / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(broken), encoding="utf-8")
    try:
        with pytest.raises(OrchestratorError, match="checkpoint"):
            run_playbook(ROOT, relative.as_posix(), ["shopify"])
    finally:
        destination.unlink(missing_ok=True)


def test_core_does_not_embed_playbook_or_physical_names() -> None:
    forbidden = (
        "monthly-business-review",
        "bluetti",
        "shopify",
        "tiktok",
        "compute_m101",
    )
    for path in (ROOT / "harness" / "core").rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden:
            assert token not in text, f"{token} in {path}"


def test_cli_smoke_and_canary(tmp_path: Path) -> None:
    evidence = tmp_path / "cli"
    result = RUNNER.invoke(
        app,
        [
            "run",
            "--playbook",
            "tests/fixtures/playbooks/echo.yaml",
            "--platform",
            "shopify",
            "--evidence-dir",
            str(evidence),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "dry_run" in result.stdout
    assert "sk-canary" not in result.stdout
    ask = RUNNER.invoke(app, ["ask"])
    assert ask.exit_code == 0
    assert json.loads(ask.stdout)["reason"] == "model key is absent"
    listed = RUNNER.invoke(app, ["playbooks"])
    assert "tests/fixtures/playbooks/echo.yaml" in listed.stdout
    help_result = RUNNER.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    escaped = RUNNER.invoke(
        app,
        ["run", "--playbook", "../outside.yaml", "--platform", "shopify"],
    )
    assert escaped.exit_code == 1
    canary = "api_key=sk-canary-secret buyer@example.com"
    assert "sk-canary-secret" not in redact_text(canary)
    assert "buyer@example.com" not in redact_text(canary)
    combined = "\n".join(path.read_text(encoding="utf-8") for path in evidence.rglob("*"))
    assert "sk-canary-secret" not in combined


def test_adapters_reject_missing_credentials_and_hostile_files(tmp_path: Path) -> None:
    missing = require_credentials(False)
    assert isinstance(missing, ErrorEnvelope)
    assert missing.code == "credentials-missing"
    assert require_credentials(True) is None
    left = canonical_snapshot("shopify", [_row("a")])
    right = canonical_snapshot("tiktok", [_row("b")])
    assert left["adapter_id"] != right["adapter_id"]
    assert left["row_count"] == 1
    for sample in (left, right):
        assert str(sample["schema_fingerprint"]).startswith("sha256:")
        assert str(sample["content_hash"]).startswith("sha256:")
        assert sample["watermark"] == "2026-01-01"
        assert sample["capability"] == {"orders": "ready"}
    assert left["unmapped_fields"] == ["a"]
    leaked = canonical_snapshot(
        "shopify",
        [{**_row("c"), "email": "buyer@example.com", "phone": "555"}],
    )
    encoded = json.dumps(leaked)
    assert "buyer@example.com" not in encoded
    assert "phone" not in encoded
    source = tmp_path / "input"
    source.mkdir()
    table = source / "facts.csv"
    table.write_text("order,1\n\n", encoding="utf-8")
    assert read_delimited_file(table, root=source) == ["order,1"]
    hostile = source / "formula.csv"
    hostile.write_text("=cmd,\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="formula"):
        read_delimited_file(hostile, root=source)
    binary = source / "binary.csv"
    binary.write_bytes(b"ok\x00bad\n")
    with pytest.raises(AdapterError, match="malicious"):
        read_delimited_file(binary, root=source)
    huge = source / "huge.csv"
    huge.write_text("x", encoding="utf-8")
    with pytest.raises(AdapterError, match="size"):
        read_delimited_file(huge, root=source, max_bytes=0)
    outside = tmp_path / "outside.csv"
    outside.write_text("x\n", encoding="utf-8")
    with pytest.raises(AdapterError, match="escapes"):
        read_delimited_file(outside, root=source)


def test_sql_guard_blocks_writes_and_hashes_bindings() -> None:
    allowed = {ORDERS}
    guarded = guard_sql(
        "SELECT item_gross_amount FROM orders WHERE order_created_date >= '2026-01-01' LIMIT 10",
        playbook=True,
        allowed_objects=allowed,
    )
    assert "2026-01-01" not in str(guarded["sql"])
    assert guarded["session"] == ["SET SESSION TRANSACTION READ ONLY"]
    bindings = guarded["bindings"]
    assert isinstance(bindings, list)
    assert all("hash" in item for item in bindings)
    with pytest.raises(SqlGuardError, match="write"):
        guard_sql("DELETE FROM orders", playbook=False, allowed_objects=allowed)
    with pytest.raises(SqlGuardError, match="write"):
        guard_sql(
            "SET SESSION TRANSACTION READ WRITE",
            playbook=False,
            allowed_objects=allowed,
        )
    with pytest.raises(SqlGuardError, match="one statement"):
        guard_sql(
            "SELECT 1 FROM orders LIMIT 1; SELECT 2 FROM orders LIMIT 1",
            playbook=False,
            allowed_objects=allowed,
        )
    with pytest.raises(SqlGuardError, match="schema"):
        guard_sql("USE other", playbook=False, allowed_objects=allowed)
    with pytest.raises(SqlGuardError, match="time window"):
        guard_sql(
            "SELECT item_gross_amount FROM orders LIMIT 5", playbook=True, allowed_objects=allowed
        )
    with pytest.raises(SqlGuardError, match="limit"):
        guard_sql(
            "SELECT item_gross_amount FROM orders WHERE order_created_date >= '2026-01-01'",
            playbook=False,
            allowed_objects=allowed,
        )
    with pytest.raises(SqlGuardError, match="allowlist"):
        guard_sql("SELECT 1 FROM other_table LIMIT 1", playbook=False, allowed_objects=allowed)
    with pytest.raises(SqlGuardError, match="credentials"):
        assert_credentials({})
    assert_credentials(
        {"MYSQL_HOST": "127.0.0.1", "MYSQL_USER": "reader", "MYSQL_PASSWORD": "placeholder"}
    )
    with pytest.raises(SqlGuardError, match="parse"):
        guard_sql("SELECT ((", playbook=False, allowed_objects=allowed)


def test_metrics_are_deterministic_and_keep_states_separate() -> None:
    facts = [
        _metric_row("1", "10.00", "-1.00", "2", product="sku-1"),
        _metric_row("2", "5.00", "0", "1", product=None),
        {
            "channel": "affiliate",
            "item_gross_amount": "99.00",
            "platform": "shopify",
            "account_id": "account",
            "order_id": "native",
        },
        {"refund_matched": False, "refund_net_effect": "-50.00", "refund_item_subtotal": "50.00"},
        {
            "refund_matched": True,
            "refund_net_effect": "-1.00",
            "refund_item_subtotal": "1.00",
            "refund_quantity": "1",
        },
    ]
    first = compute("M101", facts)
    assert first == compute("M101", facts)
    assert first["value"] == "15.00"
    assert compute("M102", facts)["value"] == "13.00"
    assert compute("M103", facts)["value"] == "2"
    assert compute("M104", facts)["value"] == "3"
    assert unmapped_products(facts) == ["2"]
    native = separate_state("platform-native", "99.00")
    assert native["in_canonical_total"] is False
    assert compute("M207a", facts)["status"] == "canonical"
    assert compute("M105", facts)["status"] == "canonical"
    assert compute("M106", facts)["status"] == "canonical"
    cancelled = [_metric_row("9", "10.00", "0", "1", product="sku-1")]
    cancelled[0]["cancelled"] = True
    blank = [_metric_row("8", "10.00", "0", "1", product="sku-1")]
    blank[0]["item_gross_amount"] = None
    assert compute("M101", blank)["value"] == "0"
    assert compute("M105", cancelled)["status"] == "diagnostic"
    with pytest.raises(MetricError, match="unsupported"):
        compute("M101", [_metric_row("1", True, "0", "1", product="sku-1")])
    with pytest.raises(MetricError):
        separate_state("canonical", "1")
    assert separate_state("provisional", None)["status"] == "provisional"
    assert separate_state("diagnostic", None)["status"] == "diagnostic"
    missing_quantity = [
        *_metric_rows_for_rate(),
        {"refund_matched": True, "refund_item_subtotal": "1.00", "refund_quantity": None},
    ]
    assert compute("M207b", missing_quantity)["status"] == "diagnostic"
    with pytest.raises(MetricError):
        compute("M999", facts)


def test_skills_do_not_need_a_playbook_context() -> None:
    skill_source = (ROOT / "harness" / "skills" / "scene.py").read_text(encoding="utf-8")
    assert "monthly-business-review" not in skill_source
    echo = run_playbook(ROOT, "tests/fixtures/playbooks/echo.yaml", ["shopify"])
    assert echo["playbook_id"] == "echo"
    closed = price_volume(Decimal(2), Decimal("10"), Decimal(3), Decimal("12"))
    assert Decimal(closed["volume"]) + Decimal(closed["price"]) + Decimal(
        closed["residual"]
    ) == Decimal(16)
    ranked = contribution([("north", Decimal(3)), ("unmapped", Decimal(1))], Decimal(4))
    assert ranked["north"] == "3"
    with pytest.raises(SkillError, match="additive"):
        contribution([("north", Decimal(3)), ("unmapped", Decimal(1))], Decimal(9))
    with pytest.raises(SkillError, match="overlap"):
        contribution([("unmapped", Decimal(1)), ("unmapped", Decimal(1))], Decimal(2))
    with pytest.raises(SkillError, match="unmapped"):
        contribution([("north", Decimal(4))], Decimal(4))
    missing = detect_anomalies(["2026-01"], None)
    assert missing["calendar_missing"] is True
    assert missing["points"][0]["in_promo_window"] is None
    marked = detect_anomalies(["2026-01"], ["2026-01"])
    assert marked["points"][0]["in_promo_window"] is True
    native = native_analysis(
        {
            "platform": "tiktok",
            "native_metric_id": "native-1",
            "official_source": "official",
            "region": "US",
            "definition_version": "1",
        }
    )
    assert native["in_canonical_total"] is False
    with pytest.raises(SkillError, match="metadata"):
        native_analysis(
            {
                "platform": "tiktok",
                "native_metric_id": "native-1",
                "official_source": "official",
                "region": "",
                "definition_version": "1",
            }
        )


def test_report_outline_and_model_port() -> None:
    package = {"numbers": {"orders": "2"}}
    sealed = seal(package)
    package["numbers"] = {"orders": "9"}
    assert validate(sealed, blocking=False)["report"] == "allowed"
    blocked = validate(sealed, blocking=True)
    assert blocked["report"] is None
    assert blocked["envelope"]["code"] == "validation-failed"
    echo = render(["echo-summary"], {"echo-summary": "2"})
    other = render(["other-section"], {"other-section": "2"})
    assert echo["markdown"] != other["markdown"]
    with pytest.raises(ValueError, match="formula"):
        render(["orders"], {"orders": "=1+1"})
    assert isinstance(complete(api_key=None, messages=[], allowlist=set()), NoOp)
    hashed = complete(
        api_key="present",
        messages=[{"role": "user", "content": "orders=2"}],
        allowlist={"content"},
    )
    assert isinstance(hashed, dict)
    assert "orders=2" not in hashed["prompt_hash"]
    with pytest.raises(LlmError):
        complete(
            api_key="present",
            messages=[{"role": "user", "raw_row": "secret"}],
            allowlist={"content"},
        )
    for module_id in ("session", "vector", "mcp", "schedule", "auth"):
        assert isinstance(disabled(module_id, module_id), NoOp)


def test_policy_blocks_restricted_egress_and_unknown_capability() -> None:
    policy = Policy(allowlist={"local"})
    with pytest.raises(PolicyError, match="restricted"):
        policy.check({"capability": "local", "network": True, "classification": "restricted"})
    with pytest.raises(PolicyError, match="allowlisted"):
        policy.check({"capability": "external", "network": False, "enforce_capability": True})
    assert (
        policy.check({"capability": "local", "network": True, "classification": "internal"})
        == "allow"
    )


def _row(order_id: str) -> dict[str, object]:
    return {
        "order_id": order_id,
        "order_created_date": "2026-01-01",
        "item_gross_amount": "10.00",
    }


def _metric_row(
    order_id: str,
    gross: str,
    discount: str,
    quantity: str,
    *,
    product: str | None,
) -> dict[str, object]:
    return {
        "platform": "shopify",
        "account_id": "account",
        "order_id": order_id,
        "item_gross_amount": gross,
        "seller_discount_amount": discount,
        "commercial_quantity": quantity,
        "product_identity": product,
        "channel": "store",
    }


def _metric_rows_for_rate() -> list[dict[str, object]]:
    return [_metric_row("1", "10.00", "0", "2", product="sku-1")]
