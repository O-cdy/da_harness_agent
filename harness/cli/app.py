"""Command line. It calls the core facade and does not own business rules."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from harness.core.contracts.models import NoOp
from harness.core.orchestrator import OrchestratorError, run_playbook
from harness.core.registry import RegistryError

app = typer.Typer(add_completion=False, no_args_is_help=True)
_PLAYBOOK = typer.Option(..., "--playbook")
_PLATFORM = typer.Option(..., "--platform")
_EVIDENCE = typer.Option("runs/cli", "--evidence-dir")


def _root() -> Path:
    return Path.cwd()


@app.command()
def run(
    playbook: str = _PLAYBOOK,
    platform: list[str] = _PLATFORM,
    evidence_dir: str = _EVIDENCE,
) -> None:
    """Run a playbook without database or model credentials."""
    try:
        result = run_playbook(
            _root(),
            playbook,
            list(platform),
            evidence_dir=_root() / evidence_dir,
        )
    except (RegistryError, OrchestratorError) as error:
        typer.echo(str(error), err=True)
        raise typer.Exit(code=1) from error
    typer.echo(json.dumps({"report_tier": "dry_run", "playbook_id": result["playbook_id"]}))


@app.command()
def ask() -> None:
    """Return a structured NoOp when no model key is configured."""
    noop = NoOp(module_id="llm", reason="model key is absent", capability="completion")
    typer.echo(noop.model_dump_json())


@app.command("playbooks")
def list_playbooks() -> None:
    """List machine playbook manifests under the repository."""
    root = _root()
    paths = sorted(root.glob("tests/fixtures/playbooks/*.yaml"))
    paths.extend(sorted(root.glob("docs/20-domain/playbooks/**/manifest.yaml")))
    for path in paths:
        typer.echo(path.relative_to(root).as_posix())
