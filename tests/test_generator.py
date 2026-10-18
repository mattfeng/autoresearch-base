from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from autoresearch_base.cli import main
from autoresearch_base.generator import ConfigurationError, generate


def test_scaffold_generates_safe_mounts_and_pi_tools(tmp_path: Path) -> None:
    project = tmp_path / "research-repo"
    project.mkdir()
    (project / ".devcontainer").mkdir()
    (project / ".devcontainer" / "devcontainer.json").write_text('{"existing": true}\n')
    workspace = project / "autoresearch"

    outcome = generate(workspace)
    assert len(outcome.written) == 10
    assert (workspace / "results" / ".gitkeep").is_file()
    assert (project / ".devcontainer" / "devcontainer.json").read_text() == '{"existing": true}\n'

    config = json.loads((workspace / ".devcontainer" / "devcontainer.json").read_text())
    assert config["workspaceFolder"] == "/workspace/autoresearch"
    assert "type=bind,readonly" in config["workspaceMount"]
    assert any("${localWorkspaceFolder}/..,target=/project,type=bind,readonly" in mount for mount in config["mounts"])
    assert any("/results,target=/results,type=bind" in mount for mount in config["mounts"])
    assert "--cap-drop=ALL" in config["runArgs"]

    launcher = (workspace / "run-pi.sh").read_text()
    assert "--no-mcp" in launcher
    assert "--no-extensions" in launcher
    assert "run_experiment,list_experiments,compare_experiments" in launcher
    assert os.access(workspace / "run-pi.sh", os.X_OK)
    assert os.access(workspace / "experiments" / "run.sh", os.X_OK)
    ext = (workspace / ".pi" / "extensions" / "experiments.ts").read_text()
    assert 'name: "run_experiment"' in ext
    assert 'name: "list_experiments"' in ext
    assert 'name: "compare_experiments"' in ext
    assert "/workspace/autoresearch/experiments/run.sh" in ext


def test_idempotence_refuses_modified_files(tmp_path: Path) -> None:
    parent = tmp_path / "repo"
    parent.mkdir()
    workspace = parent / "research"
    generate(workspace)
    assert not generate(workspace).written
    readme = workspace / "README.md"
    readme.write_text("custom")
    with pytest.raises(ConfigurationError, match="Refusing to overwrite"):
        generate(workspace)
    assert readme.read_text() == "custom"
    generate(workspace, force=True)
    assert "# research" in readme.read_text()


def test_dry_run_leaves_no_files(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    workspace = project / "autoresearch"
    result = generate(workspace, dry_run=True)
    assert len(result.written) == 10
    assert not workspace.exists()


def test_smoke_benchmark_runs_without_container(tmp_path: Path) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    (project / "src").mkdir()
    (project / "src" / "one.py").write_text("print(1)\n")
    workspace = project / "autoresearch"
    generate(workspace)
    output = tmp_path / "smoke-outputs"
    completed = subprocess.run(
        ["bash", str(workspace / "experiments" / "run.sh"), str(output), "42"],
        env={
            **os.environ,
            "AUTORESEARCH_PROJECT_DIR": str(project),
            "AUTORESEARCH_WORKSPACE_DIR": str(workspace),
        },
        capture_output=True,
        text=True,
        check=True,
    )
    metrics = json.loads((output / "metrics.json").read_text())
    assert metrics["python_source_count"] == 1
    assert metrics["seed"] == 42
    assert '"seed": 42' in completed.stdout


def test_cli_current_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "repo"
    project.mkdir()
    workspace = project / "experiments-agent"
    workspace.mkdir()
    monkeypatch.chdir(workspace)
    assert main([]) == 0
    assert (workspace / ".devcontainer" / "devcontainer.json").exists()
