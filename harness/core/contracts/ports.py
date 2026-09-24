"""Stable storage and configuration ports."""

from __future__ import annotations

from typing import Any, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from .models import ArtifactEnvelope, IdempotencyKey
from .state import RunSnapshot

ContractT = TypeVar("ContractT", bound=BaseModel)


class ConfigMigration(Protocol):
    from_version: int
    to_version: int

    def apply(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Transform one schema version without mutating its source."""
        ...


@runtime_checkable
class ConfigPort(Protocol):
    def load(self, relative_path: str, model: type[ContractT]) -> ContractT:
        """Load and strictly validate an immutable configuration contract."""
        ...

    def migrate(
        self,
        source_path: str,
        destination_path: str,
        target_model: type[ContractT],
        migration: ConfigMigration,
    ) -> ContractT:
        """Write exactly one forward version to a new immutable path."""
        ...


@runtime_checkable
class ArtifactStorePort(Protocol):
    def put(
        self,
        envelope: ArtifactEnvelope,
        payload: bytes,
        idempotency_key: IdempotencyKey,
    ) -> ArtifactEnvelope:
        """Atomically commit once for the exact idempotency key."""
        ...

    def get(self, idempotency_key: IdempotencyKey) -> ArtifactEnvelope | None:
        """Return only a fully committed artifact."""
        ...

    def read_payload(self, envelope: ArtifactEnvelope) -> bytes:
        """Read and verify committed artifact bytes."""
        ...


@runtime_checkable
class RunStateStorePort(Protocol):
    def load(self, run_id: str) -> RunSnapshot | None:
        """Load the latest committed run snapshot."""
        ...

    def compare_and_swap(
        self,
        snapshot: RunSnapshot,
        expected_revision: int | None,
    ) -> RunSnapshot:
        """Commit a new revision only when the expected revision matches."""
        ...
