"""GPU choice persistence, precedence, and cancellation through the public CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest


def configure(workspace: Path, *args: str, answers: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "autoresearch_base.cli", "--workspace", str(workspace), *args],
        input=answers,
        capture_output=True,
        text=True,
        check=False,
    )


def gpu_access(workspace: Path) -> bool:
    saved = json.loads((workspace / ".autoresearch.json").read_text())
    container = json.loads((workspace / ".devcontainer/devcontainer.json").read_text())
    assert ("--gpus=all" in container["runArgs"]) is saved["gpus"]
    return saved["gpus"]


def test_gpu_choice_persists_and_explicit_override_wins(tmp_path):
    workspace = tmp_path / "research"
    assert configure(workspace, answers="done\ny\n").returncode == 0
    assert gpu_access(workspace) is True

    assert configure(workspace, "--non-interactive").returncode == 0
    assert gpu_access(workspace) is True

    # Accepting the saved interactive default must not silently disable GPUs.
    assert configure(workspace, answers="done\n\n").returncode == 0
    assert gpu_access(workspace) is True

    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert configure(workspace, "--non-interactive", "--no-gpus", "--force", "--dry-run").returncode == 0
    assert all(path.read_bytes() == content for path, content in before.items())
    assert gpu_access(workspace) is True

    assert configure(workspace, "--non-interactive", "--no-gpus", "--force").returncode == 0
    assert gpu_access(workspace) is False

    assert configure(workspace, "--non-interactive", "--gpus", "--force").returncode == 0
    assert gpu_access(workspace) is True


@pytest.mark.parametrize("answer", ["cancel\n", ""])
def test_cancel_or_eof_at_gpu_prompt_writes_nothing(tmp_path, answer):
    workspace = tmp_path / "research"
    result = configure(workspace, "--read-only", str(tmp_path), answers=answer)
    assert result.returncode == 1
    assert not workspace.exists()


def test_invalid_answer_reprompts_and_legacy_settings_default_off(tmp_path):
    workspace = tmp_path / "research"
    result = configure(workspace, answers="done\ninvalid\n\n")
    assert result.returncode == 0
    assert gpu_access(workspace) is False

    settings = workspace / ".autoresearch.json"
    saved = json.loads(settings.read_text())
    saved.pop("gpus")
    settings.write_text(json.dumps(saved))
    assert configure(workspace, "--non-interactive", "--force").returncode == 0
    assert gpu_access(workspace) is False

    saved["gpus"] = "false"
    settings.write_text(json.dumps(saved))
    before = settings.read_bytes()
    assert configure(workspace, "--non-interactive", "--force").returncode == 2
    assert settings.read_bytes() == before
