"""Render a standalone autoresearch workspace inside an existing repository."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from jinja2 import Environment, StrictUndefined

# Template filenames avoid dot-prefixed package-data paths, so source archives
# and wheels include all of the files. Targets intentionally include dot dirs.
TEMPLATES: dict[str, str] = {
    "devcontainer/Dockerfile.j2": ".devcontainer/Dockerfile",
    "devcontainer/devcontainer.json.j2": ".devcontainer/devcontainer.json",
    "devcontainer/init-firewall.py.j2": ".devcontainer/init-firewall.py",
    "devcontainer/firewall-allowlist.txt.j2": ".devcontainer/firewall-allowlist.txt",
    "devcontainer/entrypoint.sh.j2": ".devcontainer/entrypoint.sh",
    "pi_extensions/experiments.ts.j2": ".pi/extensions/experiments.ts",
    "experiments/run.sh.j2": "experiments/run.sh",
    "experiments/benchmark.py.j2": "experiments/benchmark.py",
    "experiments/README.md.j2": "experiments/README.md",
    "AGENTS.md.j2": "AGENTS.md",
    "README.md.j2": "README.md",
    "run-pi.sh.j2": "run-pi.sh",
    "gitignore.j2": ".gitignore",
}


class ConfigurationError(ValueError):
    """Raised before writing any files when the requested configuration is unsafe."""


@dataclass(frozen=True)
class GenerationResult:
    workspace: Path
    written: tuple[Path, ...]
    unchanged: tuple[Path, ...]


def generate(
    workspace: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> GenerationResult:
    """Generate only inside a *direct child* folder of the existing project.

    A direct-child constraint keeps the Docker bind mount predictable: the
    project is always `${localWorkspaceFolder}/..` on the host.
    """
    workspace = Path(workspace).expanduser().resolve()
    project_root = workspace.parent

    if workspace == Path(workspace.anchor) or project_root == Path(project_root.anchor):
        raise ConfigurationError("Choose an experiment folder inside a project, not a filesystem root")
    if not project_root.is_dir():
        raise ConfigurationError(f"Parent project does not exist: {project_root}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", workspace.name):
        raise ConfigurationError("The experiment folder name must contain only letters, digits, ._-" )
    if workspace.name in {".", ".."}:
        raise ConfigurationError("Invalid workspace directory")
    if workspace.exists() and not workspace.is_dir():
        raise ConfigurationError(f"Experiment path is not a directory: {workspace}")
    if (workspace / "results").is_symlink():
        raise ConfigurationError("results/ must be a real directory, not a symlink")

    volume_suffix = hashlib.sha256(str(workspace).encode()).hexdigest()[:10]
    context = {
        "workspace_name": workspace.name,
        "volume_name": f"autoresearch-pi-{volume_suffix}",
    }

    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)
    templates_dir = files("autoresearch_base").joinpath("templates")
    rendered: dict[Path, str] = {}
    unchanged: list[Path] = []

    for source, destination in TEMPLATES.items():
        target = workspace / destination
        if not target.resolve().is_relative_to(workspace):
            raise ConfigurationError(f"Refusing to write through a symlink: {target}")
        template_text = templates_dir.joinpath(*source.split("/")).read_text(encoding="utf-8")
        result = env.from_string(template_text).render(**context)
        if not result.endswith("\n"):
            result += "\n"
        if target.exists():
            if not target.is_file():
                raise ConfigurationError(f"Expected an ordinary file: {target}")
            if target.read_text(encoding="utf-8") == result:
                unchanged.append(target)
                continue
            if not force:
                raise ConfigurationError(
                    f"Refusing to overwrite {target}; review edits or rerun with --force"
                )
        rendered[target] = result

    results_dir = workspace / "results"
    if results_dir.exists() and not results_dir.is_dir():
        raise ConfigurationError(f"Expected a results directory: {results_dir}")

    if not dry_run:
        workspace.mkdir(parents=True, exist_ok=True)
        results_dir.mkdir(exist_ok=True)
        for target, content in rendered.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            if target.name in {"run.sh", "run-pi.sh"}:
                target.chmod(target.stat().st_mode | 0o111)
        if not (results_dir / ".gitkeep").exists():
            (results_dir / ".gitkeep").touch()

    return GenerationResult(workspace, tuple(rendered), tuple(unchanged))
