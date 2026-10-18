"""GPU selection persistence, precedence, migration, and cancellation via the CLI."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest


def configure(workspace: Path, *args: str, answers: str = "") -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "autoresearch_base.cli", "--workspace", str(workspace), *args],
        input=answers, capture_output=True, text=True, check=False,
    )


def selection(workspace):
    return json.loads((workspace / ".autoresearch.json").read_text())["gpus"]


def runtime_request(workspace):
    container = json.loads((workspace / ".devcontainer/devcontainer.json").read_text())
    requests = [arg.removeprefix("--gpus=") for arg in container["runArgs"] if arg.startswith("--gpus=")]
    return [next(csv.reader([request])) for request in requests]


@pytest.mark.parametrize(("value", "saved", "expected_request"), [
    ("all", "all", [["all"]]),
    ("none", "none", []),
    ("0", "0", [["device=0"]]),
    ("0,2", "0,2", [["device=0,2"]]),
    (" 02, 0,2 ", "2,0", [["device=2,0"]]),
    ("GPU-18a3e86f-4c0e-cd9f-59c3-55488c4b0c24", "GPU-18a3e86f-4c0e-cd9f-59c3-55488c4b0c24", [["device=GPU-18a3e86f-4c0e-cd9f-59c3-55488c4b0c24"]]),
    ("MIG-GPU-18a3e86f/1/0", "MIG-GPU-18a3e86f/1/0", [["device=MIG-GPU-18a3e86f/1/0"]]),
])
def test_explicit_selection_has_correct_docker_csv_semantics(tmp_path, value, saved, expected_request):
    workspace = tmp_path / "research"
    result = configure(workspace, "--read-only", str(tmp_path), "--gpus", value)
    assert result.returncode == 0, result.stderr
    assert selection(workspace) == saved
    assert runtime_request(workspace) == expected_request


def test_selection_persists_and_override_dry_run_does_not_write(tmp_path):
    workspace = tmp_path / "research"
    assert configure(workspace, answers="done\n0,2\n").returncode == 0
    assert selection(workspace) == "0,2"
    assert configure(workspace, "--non-interactive").returncode == 0
    assert runtime_request(workspace) == [["device=0,2"]]
    assert configure(workspace, answers="done\n\n").returncode == 0
    assert selection(workspace) == "0,2"

    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert configure(workspace, "--non-interactive", "--gpus", "none", "--force", "--dry-run").returncode == 0
    assert all(path.read_bytes() == content for path, content in before.items())
    assert configure(workspace, "--non-interactive", "--gpus", "none", "--force").returncode == 0
    assert selection(workspace) == "none"
    assert runtime_request(workspace) == []
    assert configure(workspace, "--non-interactive", "--gpus", "all", "--force").returncode == 0
    assert runtime_request(workspace) == [["all"]]


@pytest.mark.parametrize("answer", ["cancel\n", ""])
def test_cancel_or_eof_at_gpu_prompt_writes_nothing(tmp_path, answer):
    workspace = tmp_path / "research"
    result = configure(workspace, "--read-only", str(tmp_path), answers=answer)
    assert result.returncode == 1
    assert not workspace.exists()


def test_invalid_answer_reprompts_and_empty_selection_defaults_to_none(tmp_path):
    workspace = tmp_path / "research"
    result = configure(workspace, answers="done\ninvalid\n\n")
    assert result.returncode == 0
    assert selection(workspace) == "none"
    assert runtime_request(workspace) == []


@pytest.mark.parametrize(("legacy", "expected", "expected_request"), [
    (True, "all", [["all"]]), (False, "none", []), (None, "none", []),
])
def test_saved_boolean_or_missing_selection_migrates(tmp_path, legacy, expected, expected_request):
    workspace = tmp_path / "research"
    assert configure(workspace, answers="done\nnone\n").returncode == 0
    settings = workspace / ".autoresearch.json"
    saved = json.loads(settings.read_text())
    if legacy is None:
        saved.pop("gpus")
    else:
        saved["gpus"] = legacy
    settings.write_text(json.dumps(saved))
    assert configure(workspace, "--non-interactive", "--force").returncode == 0
    assert selection(workspace) == expected
    assert runtime_request(workspace) == expected_request


@pytest.mark.parametrize("value", ["", "all,0", "0,", "-1", "0,,2", "device=0", "0\n2"])
def test_invalid_explicit_selection_writes_nothing(tmp_path, value):
    workspace = tmp_path / "research"
    result = configure(workspace, "--read-only", str(tmp_path), "--gpus", value)
    assert result.returncode == 2
    assert not workspace.exists()


@pytest.mark.parametrize("value", [5, [], None, "false"])
def test_invalid_saved_selection_preserves_workspace(tmp_path, value):
    workspace = tmp_path / "research"
    assert configure(workspace, answers="done\nnone\n").returncode == 0
    settings = workspace / ".autoresearch.json"
    saved = json.loads(settings.read_text())
    saved["gpus"] = value
    settings.write_text(json.dumps(saved))
    before = {path: path.read_bytes() for path in workspace.rglob("*") if path.is_file()}
    assert configure(workspace, "--non-interactive", "--force").returncode == 2
    assert all(path.read_bytes() == content for path, content in before.items())
