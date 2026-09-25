"""Traversal-safe, crash-consistent file stores."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
import stat
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from uuid import uuid4

from harness.core.contracts.models import (
    ArtifactEnvelope,
    IdempotencyKey,
    StrictContract,
)
from harness.core.contracts.ports import ConfigMigration, ContractT
from harness.core.contracts.state import (
    InvalidRunTransition,
    ReportTier,
    RunSnapshot,
    RunStatus,
    assert_branch_commit,
    transition_run,
)

__all__ = [
    "ConfigMigrationError",
    "FileArtifactStore",
    "FileConfigStore",
    "FileRunStateStore",
    "IdempotencyConflict",
    "IdempotencyKey",
    "PathBoundaryError",
    "RevisionConflict",
]


class PathBoundaryError(ValueError):
    """A requested path could escape its configured root."""


class RevisionConflict(RuntimeError):
    """A compare-and-swap observed a different committed revision."""


class ConfigMigrationError(ValueError):
    """A config migration violated immutable sequential versioning."""


class ArtifactIntegrityError(RuntimeError):
    """Committed artifact bytes do not match their envelope."""


class IdempotencyConflict(RuntimeError):
    """An idempotency key was reused with different content."""


class _ArtifactRecord(StrictContract):
    idempotency_key: IdempotencyKey
    envelope: ArtifactEnvelope
    payload_base64: str


_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.Lock] = {}
_WINDOWS_DEVICES = frozenset(
    {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        "CONIN$",
        "CONOUT$",
        *(f"COM{index}" for index in range(1, 10)),
        *(f"LPT{index}" for index in range(1, 10)),
    }
)
_WINDOWS_FORBIDDEN_CHARS = frozenset('<>:"|?*')
_REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)


@contextmanager
def _exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCKS_GUARD:
        thread_lock = _THREAD_LOCKS.setdefault(path.resolve(), threading.Lock())
    with thread_lock, path.open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
        else:
            fcntl: Any = importlib.import_module("fcntl")
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            stream.seek(0)
            if sys.platform == "win32":
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _safe_path(root: Path, relative_path: str) -> Path:
    windows = PureWindowsPath(relative_path)
    posix = PurePosixPath(relative_path)
    if windows.is_absolute() or posix.is_absolute():
        raise PathBoundaryError(f"absolute path rejected: {relative_path}")
    if ".." in windows.parts or ".." in posix.parts:
        raise PathBoundaryError(f"path traversal rejected: {relative_path}")
    for component in windows.parts:
        _validate_portable_component(component)
    candidate = (root / Path(relative_path)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise PathBoundaryError(f"path outside root rejected: {relative_path}") from error
    return candidate


def _is_reparse_point(path: Path) -> bool:
    try:
        info = path.lstat()
    except OSError:
        return False
    if stat.S_ISLNK(info.st_mode):
        return True
    attributes = getattr(info, "st_file_attributes", 0)
    return bool(attributes & _REPARSE_POINT)


def trusted_directory(root: Path) -> Path:
    """Return an absolute store root whose ancestors are not symlinks or junctions."""
    absolute = Path(os.path.abspath(root))
    cursor = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        cursor = cursor / part
        if _is_reparse_point(cursor):
            raise PathBoundaryError(f"refusing redirected store path: {cursor}")
    return absolute


def _validate_portable_component(component: str) -> None:
    if (
        not component
        or component.endswith((".", " "))
        or any(ord(character) < 32 for character in component)
        or any(character in _WINDOWS_FORBIDDEN_CHARS for character in component)
    ):
        raise PathBoundaryError(f"unsafe path component: {component!r}")
    normalized = component.rstrip(" .")
    device_stem = normalized.split(".", 1)[0].strip().upper()
    if device_stem in _WINDOWS_DEVICES or normalized.strip().upper() in _WINDOWS_DEVICES:
        raise PathBoundaryError(f"reserved Windows device name: {component}")


def _safe_identifier(value: str, label: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise PathBoundaryError(f"unsafe {label}")
    _validate_portable_component(value)
    return value


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        if os.name != "nt":
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        with suppress(FileNotFoundError):
            temporary.unlink()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _key_digest(key: IdempotencyKey) -> str:
    return hashlib.sha256(_json_bytes(key.model_dump(mode="json"))).hexdigest()


def _verify_content(envelope: ArtifactEnvelope, payload: bytes) -> None:
    expected = f"sha256:{hashlib.sha256(payload).hexdigest()}"
    if envelope.content_hash != expected:
        raise ArtifactIntegrityError("artifact content hash mismatch")


class FileConfigStore:
    def __init__(self, root: Path) -> None:
        self._root = trusted_directory(root)

    def load(self, relative_path: str, model: type[ContractT]) -> ContractT:
        path = _safe_path(self._root, relative_path)
        return model.model_validate_json(path.read_bytes())

    def migrate(
        self,
        source_path: str,
        destination_path: str,
        target_model: type[ContractT],
        migration: ConfigMigration,
    ) -> ContractT:
        source = _safe_path(self._root, source_path)
        destination = _safe_path(self._root, destination_path)
        if source == destination:
            raise ConfigMigrationError("config migration cannot run in place")
        if destination.exists():
            raise ConfigMigrationError("migration destination already exists")
        raw = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ConfigMigrationError("config root must be an object")
        source_version = raw.get("schema_version")
        if (
            isinstance(source_version, bool)
            or not isinstance(source_version, int)
            or source_version != migration.from_version
        ):
            raise ConfigMigrationError("unknown source schema_version")
        if migration.to_version != migration.from_version + 1:
            raise ConfigMigrationError("migration versions must be sequential and forward")
        try:
            transformed = migration.apply(dict(raw))
        except Exception as error:
            raise ConfigMigrationError("migration transform failed") from error
        if not isinstance(transformed, dict):
            raise ConfigMigrationError("migration output must be an object")
        if transformed.get("schema_version") != migration.to_version:
            raise ConfigMigrationError("migration emitted invalid target schema_version")
        try:
            validated = target_model.model_validate(transformed)
        except ValueError as error:
            raise ConfigMigrationError("migration output failed target validation") from error
        with _exclusive_lock(destination.with_suffix(".lock")):
            if destination.exists():
                raise ConfigMigrationError("migration destination already exists")
            _atomic_write(destination, validated.model_dump_json().encode())
        return validated


class FileArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = trusted_directory(root)
        self._artifact_root = self._root / "artifacts"

    def _path(self, key: IdempotencyKey) -> Path:
        return _safe_path(self._artifact_root, f"{_key_digest(key)}.json")

    def put(
        self,
        envelope: ArtifactEnvelope,
        payload: bytes,
        idempotency_key: IdempotencyKey,
    ) -> ArtifactEnvelope:
        path = self._path(idempotency_key)
        with _exclusive_lock(path.with_suffix(".lock")):
            existing = self._load_record(idempotency_key)
            if existing is not None:
                existing_payload = base64.b64decode(existing.payload_base64, validate=True)
                if existing.envelope == envelope and existing_payload == payload:
                    self._remember(envelope.artifact_id, path.name)
                    return existing.envelope
                raise IdempotencyConflict(
                    "idempotency key already committed with different envelope or payload"
                )
            _verify_content(envelope, payload)
            record = _ArtifactRecord(
                idempotency_key=idempotency_key,
                envelope=envelope,
                payload_base64=base64.b64encode(payload).decode("ascii"),
            )
            _atomic_write(path, record.model_dump_json().encode())
            self._remember(envelope.artifact_id, path.name)
            return envelope

    def _load_record(self, idempotency_key: IdempotencyKey) -> _ArtifactRecord | None:
        path = self._path(idempotency_key)
        if not path.is_file():
            return None
        record = _ArtifactRecord.model_validate_json(path.read_bytes())
        if record.idempotency_key != idempotency_key:
            raise ArtifactIntegrityError("idempotency key mismatch")
        payload = base64.b64decode(record.payload_base64, validate=True)
        _verify_content(record.envelope, payload)
        return record

    def get(self, idempotency_key: IdempotencyKey) -> ArtifactEnvelope | None:
        record = self._load_record(idempotency_key)
        return record.envelope if record is not None else None

    def _index_path(self) -> Path:
        return self._artifact_root / "_index.json"

    def _remember(self, artifact_id: str, filename: str) -> None:
        index_path = self._index_path()
        with _exclusive_lock(index_path.with_suffix(".lock")):
            current: dict[str, str] = {}
            if index_path.is_file():
                loaded = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    current = {
                        str(key): str(value)
                        for key, value in loaded.items()
                        if isinstance(key, str) and isinstance(value, str)
                    }
            current[artifact_id] = filename
            _atomic_write(index_path, json.dumps(current, sort_keys=True).encode())

    def read_payload(self, envelope: ArtifactEnvelope) -> bytes:
        index_path = self._index_path()
        if not index_path.is_file():
            raise FileNotFoundError(envelope.artifact_id)
        loaded = json.loads(index_path.read_text(encoding="utf-8"))
        filename = loaded.get(envelope.artifact_id) if isinstance(loaded, dict) else None
        if not isinstance(filename, str):
            raise FileNotFoundError(envelope.artifact_id)
        path = _safe_path(self._artifact_root, filename)
        record = _ArtifactRecord.model_validate_json(path.read_bytes())
        if record.envelope != envelope:
            raise ArtifactIntegrityError("artifact index does not match envelope")
        payload = base64.b64decode(record.payload_base64, validate=True)
        _verify_content(record.envelope, payload)
        return payload


class FileRunStateStore:
    def __init__(self, root: Path) -> None:
        self._root = trusted_directory(root)
        self._state_root = self._root / "run-state"

    def _path(self, run_id: str) -> Path:
        safe_id = _safe_identifier(run_id, "run_id")
        return _safe_path(self._state_root, f"{safe_id}.json")

    def load(self, run_id: str) -> RunSnapshot | None:
        path = self._path(run_id)
        if not path.is_file():
            return None
        return RunSnapshot.model_validate_json(path.read_bytes())

    def compare_and_swap(
        self,
        snapshot: RunSnapshot,
        expected_revision: int | None,
    ) -> RunSnapshot:
        path = self._path(snapshot.run_id)
        with _exclusive_lock(path.with_suffix(".lock")):
            current = self.load(snapshot.run_id)
            current_revision = current.revision if current is not None else None
            if current_revision != expected_revision:
                raise RevisionConflict(
                    f"revision conflict: expected {expected_revision}, found {current_revision}"
                )
            candidate = RunSnapshot.model_validate(snapshot.model_dump())
            expected_candidate_revision = expected_revision if expected_revision is not None else 0
            if candidate.revision != expected_candidate_revision:
                raise RevisionConflict(
                    "candidate revision must match expected/current revision: "
                    f"{candidate.revision} != {expected_candidate_revision}"
                )
            if current is None:
                if (
                    candidate.run_status is not RunStatus.CREATED
                    or candidate.plan_revision != 1
                    or candidate.report_tier is not ReportTier.DRY_RUN
                    or candidate.branches
                    or candidate.checkpoint is not None
                ):
                    raise InvalidRunTransition(
                        "initial run snapshot must be pristine created state"
                    )
            elif candidate.branches != current.branches:
                assert_branch_commit(current, candidate)
            elif candidate.run_status is current.run_status:
                if current.run_status in {
                    RunStatus.COMPLETED,
                    RunStatus.CANCELLED,
                    RunStatus.FAILED,
                }:
                    transition_run(current, candidate.run_status)
                if candidate.plan_revision != current.plan_revision:
                    raise InvalidRunTransition("in-state update cannot change plan_revision")
            else:
                validated = transition_run(
                    current,
                    candidate.run_status,
                    checkpoint=candidate.checkpoint,
                    error=candidate.error,
                )
                control_fields = (
                    "run_status",
                    "plan_revision",
                    "checkpoint",
                    "resume_status",
                    "error",
                )
                if any(
                    getattr(candidate, field) != getattr(validated, field)
                    for field in control_fields
                ):
                    raise InvalidRunTransition("candidate does not match state-machine transition")
            committed = candidate.model_copy(update={"revision": (current_revision or 0) + 1})
            _atomic_write(path, committed.model_dump_json().encode())
            return committed
