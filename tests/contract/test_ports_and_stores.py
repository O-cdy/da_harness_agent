import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import BaseModel, ConfigDict

from harness.core.contracts.models import (
    ArtifactClassification,
    ArtifactEnvelope,
    DataCompleteness,
    NoOp,
)
from harness.core.contracts.ports import (
    ArtifactStorePort,
    ConfigPort,
    RunStateStorePort,
)
from harness.core.contracts.state import ReportTier, RunSnapshot, RunStatus
from harness.core.storage.files import (
    ArtifactIntegrityError,
    ConfigMigrationError,
    FileArtifactStore,
    FileConfigStore,
    FileRunStateStore,
    IdempotencyKey,
    PathBoundaryError,
    RevisionConflict,
)


class ConfigV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    value: str


class ConfigV2(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[2]
    value: str
    normalized: bool


class V1ToV2:
    from_version = 1
    to_version = 2

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {**payload, "schema_version": 2, "normalized": True}


def artifact(payload: bytes, artifact_id: str = "artifact-1") -> ArtifactEnvelope:
    digest = hashlib.sha256(payload).hexdigest()
    return ArtifactEnvelope(
        artifact_id=artifact_id,
        type="binary",
        content_hash=f"sha256:{digest}",
        producer="contract-test",
        input_refs=[],
        created_at=datetime.now(UTC),
        classification=ArtifactClassification.INTERNAL,
        revision=1,
    )


def idem() -> IdempotencyKey:
    return IdempotencyKey(
        run_id="run-1",
        plan_revision=1,
        step_id="step-1",
        input_fingerprint="sha256:input",
    )


def snapshot(revision: int = 0) -> RunSnapshot:
    return RunSnapshot(
        run_id="run-1",
        plan_revision=1,
        revision=revision,
        run_status=RunStatus.CREATED,
        data_completeness=DataCompleteness.PARTIAL,
        report_tier=ReportTier.DRY_RUN,
    )


def test_file_implementations_satisfy_runtime_ports(tmp_path: Path) -> None:
    assert isinstance(FileConfigStore(tmp_path), ConfigPort)
    assert isinstance(FileArtifactStore(tmp_path), ArtifactStorePort)
    assert isinstance(FileRunStateStore(tmp_path), RunStateStorePort)


@pytest.mark.parametrize("unsafe", ["../escape.json", "/absolute.json", r"C:\absolute.json"])
def test_config_paths_reject_traversal_and_absolute_paths(tmp_path: Path, unsafe: str) -> None:
    with pytest.raises(PathBoundaryError):
        FileConfigStore(tmp_path).load(unsafe, NoOp)


def test_config_loading_uses_strict_contract_validation(tmp_path: Path) -> None:
    (tmp_path / "noop.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module_id": "llm",
                "reason": "disabled",
                "capability": "completion",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError):
        FileConfigStore(tmp_path).load("noop.json", NoOp)

    (tmp_path / "valid.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module_id": "llm",
                "reason": "disabled",
                "capability": "completion",
            }
        ),
        encoding="utf-8",
    )
    assert FileConfigStore(tmp_path).load("valid.json", NoOp).module_id == "llm"


def test_config_migration_writes_new_immutable_version(tmp_path: Path) -> None:
    source = tmp_path / "profile-v1.json"
    source.write_text('{"schema_version":1,"value":"raw"}', encoding="utf-8")
    store = FileConfigStore(tmp_path)

    migrated = store.migrate(
        "profile-v1.json",
        "profile-v2.json",
        ConfigV2,
        V1ToV2(),
    )

    assert migrated == ConfigV2(schema_version=2, value="raw", normalized=True)
    assert json.loads(source.read_text(encoding="utf-8"))["schema_version"] == 1
    assert (
        json.loads((tmp_path / "profile-v2.json").read_text(encoding="utf-8"))["schema_version"]
        == 2
    )

    with pytest.raises(ConfigMigrationError, match="already exists"):
        store.migrate("profile-v1.json", "profile-v2.json", ConfigV2, V1ToV2())


def test_config_migration_rejects_in_place_unknown_and_nonsequential_steps(
    tmp_path: Path,
) -> None:
    (tmp_path / "profile-v1.json").write_text(
        '{"schema_version":1,"value":"raw"}',
        encoding="utf-8",
    )
    store = FileConfigStore(tmp_path)

    with pytest.raises(ConfigMigrationError, match="in place"):
        store.migrate("profile-v1.json", "profile-v1.json", ConfigV2, V1ToV2())

    class UnknownToNext(V1ToV2):
        from_version = 7
        to_version = 8

    with pytest.raises(ConfigMigrationError, match="unknown source"):
        store.migrate("profile-v1.json", "unknown.json", ConfigV2, UnknownToNext())

    class Downgrade(V1ToV2):
        from_version = 1
        to_version = 0

    with pytest.raises(ConfigMigrationError, match="sequential"):
        store.migrate("profile-v1.json", "down.json", ConfigV2, Downgrade())

    class Skip(V1ToV2):
        from_version = 1
        to_version = 3

    with pytest.raises(ConfigMigrationError, match="sequential"):
        store.migrate("profile-v1.json", "skip.json", ConfigV2, Skip())


def test_config_migration_rejects_invalid_transformed_payload(tmp_path: Path) -> None:
    (tmp_path / "profile-v1.json").write_text(
        '{"schema_version":1,"value":"raw"}',
        encoding="utf-8",
    )

    class InvalidMigration(V1ToV2):
        def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {**payload, "normalized": True}

    with pytest.raises(ConfigMigrationError, match="target schema_version"):
        FileConfigStore(tmp_path).migrate(
            "profile-v1.json",
            "invalid.json",
            ConfigV2,
            InvalidMigration(),
        )
    assert not (tmp_path / "invalid.json").exists()

    class NonObjectMigration(V1ToV2):
        def apply(self, payload: dict[str, Any]) -> Any:
            return ["not", "an", "object"]

    with pytest.raises(ConfigMigrationError, match="object"):
        FileConfigStore(tmp_path).migrate(
            "profile-v1.json",
            "non-object.json",
            ConfigV2,
            NonObjectMigration(),
        )
    assert not (tmp_path / "non-object.json").exists()


def test_artifact_put_is_idempotent_without_duplicate_side_effects(tmp_path: Path) -> None:
    store = FileArtifactStore(tmp_path)
    first = store.put(artifact(b"first"), b"first", idem())
    second = store.put(artifact(b"second", "artifact-2"), b"second", idem())

    assert first == second
    assert store.get(idem()) == first
    assert store.read_payload(first) == b"first"
    assert len(list((tmp_path / "artifacts").glob("*.json"))) == 1


def test_crash_tmp_is_not_committed_and_retry_recovers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileArtifactStore(tmp_path)
    real_replace = __import__("harness.core.storage.files", fromlist=["os"]).os.replace

    def crash_replace(source: str | Path, target: str | Path) -> None:
        raise OSError("simulated crash")

    monkeypatch.setattr("harness.core.storage.files.os.replace", crash_replace)
    with pytest.raises(OSError, match="simulated crash"):
        store.put(artifact(b"payload"), b"payload", idem())
    assert store.get(idem()) is None

    monkeypatch.setattr("harness.core.storage.files.os.replace", real_replace)
    committed = store.put(artifact(b"payload"), b"payload", idem())
    assert store.read_payload(committed) == b"payload"


def test_orphan_tmp_file_is_never_visible_as_artifact(tmp_path: Path) -> None:
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "orphan.tmp").write_text("partial", encoding="utf-8")

    assert FileArtifactStore(tmp_path).get(idem()) is None


def test_artifact_content_hash_is_verified_and_missing_payload_is_explicit(
    tmp_path: Path,
) -> None:
    store = FileArtifactStore(tmp_path)
    with pytest.raises(ArtifactIntegrityError, match="hash mismatch"):
        store.put(artifact(b"expected"), b"different", idem())

    with pytest.raises(FileNotFoundError):
        store.read_payload(artifact(b"missing"))


def test_run_state_store_uses_revision_compare_and_swap(tmp_path: Path) -> None:
    store = FileRunStateStore(tmp_path)
    first = store.compare_and_swap(snapshot(), expected_revision=None)
    assert first.revision == 1

    with pytest.raises(RevisionConflict):
        store.compare_and_swap(first, expected_revision=0)

    second = store.compare_and_swap(first, expected_revision=1)
    assert second.revision == 2
    assert store.load("run-1") == second


def test_run_ids_cannot_escape_store_root(tmp_path: Path) -> None:
    with pytest.raises(PathBoundaryError):
        FileRunStateStore(tmp_path).load("../run")
    assert FileRunStateStore(tmp_path).load("not-created") is None


def test_revision_cas_allows_only_one_concurrent_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FileRunStateStore(tmp_path)
    first = store.compare_and_swap(snapshot(), expected_revision=None)
    files_module = __import__("harness.core.storage.files", fromlist=["_atomic_write"])
    real_atomic_write = files_module._atomic_write

    def slow_atomic_write(path: Path, payload: bytes) -> None:
        time.sleep(0.05)
        real_atomic_write(path, payload)

    monkeypatch.setattr("harness.core.storage.files._atomic_write", slow_atomic_write)

    def attempt() -> bool:
        try:
            store.compare_and_swap(first, expected_revision=1)
        except RevisionConflict:
            return False
        return True

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: attempt(), range(4)))

    assert results.count(True) == 1
