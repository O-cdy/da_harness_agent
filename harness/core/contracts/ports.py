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


@runtime_checkable
class PlaybookPort(Protocol):
    def load(self, playbook_id: str) -> dict[str, Any]:
        """Read one playbook's machine steps."""
        ...


@runtime_checkable
class PlatformAdapterPort(Protocol):
    def snapshot(self, platform_id: str) -> dict[str, Any]:
        """Extract, normalize, and report capability for one platform."""
        ...


@runtime_checkable
class MetricPort(Protocol):
    def compute(self, metric_ref: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
        """Compute one registered metric from canonical facts."""
        ...


@runtime_checkable
class RulePackPort(Protocol):
    def resolve(self, selected: list[str]) -> dict[str, str]:
        """Resolve rule packs by scope."""
        ...


@runtime_checkable
class SkillPort(Protocol):
    def run(self, skill_id: str, facts: list[dict[str, Any]]) -> dict[str, Any]:
        """Run one skill against already-canonical facts."""
        ...


@runtime_checkable
class ToolPort(Protocol):
    def invoke(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Invoke one registered tool."""
        ...


@runtime_checkable
class LlmPort(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """Complete from an allowlist, or return NoOp when no key is configured."""
        ...


@runtime_checkable
class IngestPort(Protocol):
    def snapshot(self, plan_id: str) -> dict[str, Any]:
        """Capture a source manifest for one plan."""
        ...


@runtime_checkable
class ExecutorPort(Protocol):
    def execute(self, plan_id: str) -> dict[str, Any]:
        """Execute a plan against an already captured manifest."""
        ...


@runtime_checkable
class ValidatorPort(Protocol):
    def assert_(self, content_hash: str) -> dict[str, Any]:
        """Assert a sealed artifact package."""
        ...


@runtime_checkable
class EvaluatorPort(Protocol):
    def score(self, content_hash: str) -> dict[str, Any]:
        """Score a sealed package without reopening its inputs."""
        ...


@runtime_checkable
class ReporterPort(Protocol):
    def render(self, outline: list[str]) -> dict[str, str]:
        """Render the outline carried by the current plan."""
        ...


@runtime_checkable
class MemoryPort(Protocol):
    def assemble(self, task_id: str) -> dict[str, Any]:
        """Assemble caliber and error references without prior metric numbers."""
        ...


@runtime_checkable
class PolicyPort(Protocol):
    def check(self, event: dict[str, Any]) -> str:
        """Allow or deny one tool event."""
        ...


@runtime_checkable
class TracePort(Protocol):
    def span(self, name: str) -> None:
        """Record one trace span."""
        ...


@runtime_checkable
class ApprovalPort(Protocol):
    def fingerprint(self, payload: dict[str, Any]) -> str:
        """Build the approval fingerprint for one run."""
        ...


@runtime_checkable
class McpPort(Protocol):
    def invoke(self, name: str) -> dict[str, Any]:
        """No-op until a separate ADR enables MCP."""
        ...


@runtime_checkable
class SchedulePort(Protocol):
    def status(self) -> dict[str, Any]:
        """No-op until a separate ADR enables scheduling."""
        ...


@runtime_checkable
class AuthPort(Protocol):
    def status(self) -> dict[str, Any]:
        """No-op until a separate ADR enables interactive auth."""
        ...


@runtime_checkable
class SessionPort(Protocol):
    def load(self, session_id: str) -> dict[str, Any]:
        """No-op until a separate ADR enables session storage."""
        ...


@runtime_checkable
class VectorPort(Protocol):
    def search(self, query: str) -> dict[str, Any]:
        """No-op until a separate ADR enables a vector store."""
        ...
