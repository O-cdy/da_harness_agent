"""Traversal-safe, crash-consistent file stores."""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import os
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
from harness.core.contracts.ports import ContractT
from harness.core.contracts.state import RunSnapshot

__all__ = [
    "FileArtifactStore",
    "FileConfigStore",
    "FileRunStateStore",
    "IdempotencyKey",
    "PathBoundaryError",
    "RevisionConflict",
]


class PathBoundaryError(ValueError):
    """A requested path could escape its configured root."""


class RevisionConflict(RuntimeError):
    """A compare-and-swap observed a different committed revision."""


class ArtifactIntegrityError(RuntimeError):
    """Committed artifact bytes do not match their envelope."""


class _ArtifactRecord(StrictContract):
    idempotency_key: IdempotencyKey
    envelope: ArtifactEnvelope
    payload_base64: str


_LOCKS_GUARD = threading.Lock()
_THREAD_LOCKS: dict[Path, threading.Lock] = {}


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
    candidate = (root / Path(relative_path)).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError as error:
        raise PathBoundaryError(f"path outside root rejected: {relative_path}") from error
    return candidate


def _safe_identifier(value: str, label: str) -> str:
    if not value or value in {".", ".."} or "/" in value or "\\" in value:
        raise PathBoundaryError(f"unsafe {label}")
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
        self._root = root.resolve()

    def load(self, relative_path: str, model: type[ContractT]) -> ContractT:
        path = _safe_path(self._root, relative_path)
        return model.model_validate_json(path.read_bytes())


class FileArtifactStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
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
            existing = self.get(idempotency_key)
            if existing is not None:
                return existing
            _verify_content(envelope, payload)
            record = _ArtifactRecord(
                idempotency_key=idempotency_key,
                envelope=envelope,
                payload_base64=base64.b64encode(payload).decode("ascii"),
            )
            _atomic_write(path, record.model_dump_json().encode())
            return envelope

    def get(self, idempotency_key: IdempotencyKey) -> ArtifactEnvelope | None:
        path = self._path(idempotency_key)
        if not path.is_file():
            return None
        record = _ArtifactRecord.model_validate_json(path.read_bytes())
        if record.idempotency_key != idempotency_key:
            raise ArtifactIntegrityError("idempotency key mismatch")
        payload = base64.b64decode(record.payload_base64, validate=True)
        _verify_content(record.envelope, payload)
        return record.envelope

    def read_payload(self, envelope: ArtifactEnvelope) -> bytes:
        if not self._artifact_root.is_dir():
            raise FileNotFoundError(envelope.artifact_id)
        for path in self._artifact_root.glob("*.json"):
            record = _ArtifactRecord.model_validate_json(path.read_bytes())
            if record.envelope == envelope:
                payload = base64.b64decode(record.payload_base64, validate=True)
                _verify_content(record.envelope, payload)
                return payload
        raise FileNotFoundError(envelope.artifact_id)


class FileRunStateStore:
    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
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
            committed = snapshot.model_copy(update={"revision": (current_revision or 0) + 1})
            _atomic_write(path, committed.model_dump_json().encode())
            return committed
