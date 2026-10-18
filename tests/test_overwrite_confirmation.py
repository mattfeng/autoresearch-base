"""Interactive regeneration requires consent before replacing existing files."""

import json
import subprocess
import sys

import pytest


def configure(workspace, *args, answers=""):
    return subprocess.run(
        [sys.executable, "-m", "autoresearch_base.cli", "--workspace", str(workspace), *args],
        input=answers, capture_output=True, text=True, check=False,
    )


def prepare_workspace(tmp_path):
    workspace = tmp_path / "research"
    result = configure(workspace, answers="done\nnone\n")
    assert result.returncode == 0, result.stderr
    dockerfile = workspace / ".devcontainer/Dockerfile"
    original = dockerfile.read_bytes()
    dockerfile.write_bytes(original + b"\n# local customization\n")
    return workspace, dockerfile, original


def test_confirmation_after_choices_replaces_files_and_applies_gpu_choice(tmp_path):
    workspace, dockerfile, original = prepare_workspace(tmp_path)
    obsolete = workspace / "run-pi.sh"
    obsolete.write_text("local runner\n")
    result = configure(workspace, answers="done\nall\ninvalid\nyes\n")
    assert result.returncode == 0, result.stderr
    assert dockerfile.read_bytes() == original
    assert json.loads((workspace / ".autoresearch.json").read_text())["gpus"] == "all"
    assert "--gpus=all" in json.loads((workspace / ".devcontainer/devcontainer.json").read_text())["runArgs"]
    assert not obsolete.exists()


@pytest.mark.parametrize("answer", ["n\n", "\n", "cancel\n", ""])
def test_decline_or_eof_preserves_entire_workspace(tmp_path, answer):
    workspace, _, _ = prepare_workspace(tmp_path)
    before = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    result = configure(workspace, answers="done\nall\n" + answer)
    assert result.returncode == 1
    after = {path.relative_to(workspace): path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert after == before


def test_non_interactive_still_requires_force(tmp_path):
    workspace, dockerfile, original = prepare_workspace(tmp_path)
    modified = dockerfile.read_bytes()
    assert configure(workspace, "--non-interactive").returncode == 2
    assert dockerfile.read_bytes() == modified
    assert configure(workspace, "--non-interactive", "--force").returncode == 0
    assert dockerfile.read_bytes() == original


def test_dry_run_previews_changes_without_confirmation_or_writes(tmp_path):
    workspace, dockerfile, _ = prepare_workspace(tmp_path)
    modified = dockerfile.read_bytes()
    result = configure(workspace, "--dry-run", answers="done\nall\n")
    assert result.returncode == 0, result.stderr
    assert dockerfile.read_bytes() == modified
    assert json.loads((workspace / ".autoresearch.json").read_text())["gpus"] == "none"
