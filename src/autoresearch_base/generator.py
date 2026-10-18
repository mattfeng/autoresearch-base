"""Render a standalone autoresearch workspace with explicitly selected source mounts."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
import os
import json
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
    "devcontainer/init-gpu.py.j2": ".devcontainer/init-gpu.py",
    "devcontainer/firewall-allowlist.txt.j2": ".devcontainer/firewall-allowlist.txt",
    "devcontainer/entrypoint.sh.j2": ".devcontainer/entrypoint.sh",
    "devcontainer/init-node.py.j2": ".devcontainer/init-node.py",
    "pi_settings.json.j2": ".devcontainer/pi-settings.json",
    "AGENTS.md.j2": "AGENTS.md",
    "README.md.j2": "README.md",
    "gitignore.j2": ".gitignore",
    "settings.json.j2": ".autoresearch.json",
}


class ConfigurationError(ValueError):
    """Raised before writing any files when the requested configuration is unsafe."""


@dataclass(frozen=True)
class ReadOnlyMount:
    source: Path
    target: str
    relative_source: str


def _validate_mount_path(path: Path | str) -> None:
    text = str(path)
    if any(character in text for character in (",", "\n", "\r", '"', "${")):
        raise ConfigurationError(f"Unsupported Docker mount path: {text!r}")


def validate_workspace(workspace: Path) -> Path:
    """Admit only new, empty, or identifiable autoresearch workspaces."""
    _validate_mount_path(workspace)
    workspace = Path(workspace).expanduser().resolve()
    _validate_mount_path(workspace)
    if workspace == Path(workspace.anchor):
        raise ConfigurationError("Choose an experiment folder, not a filesystem root")
    if not workspace.parent.is_dir():
        raise ConfigurationError(f"Workspace parent does not exist: {workspace.parent}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", workspace.name):
        raise ConfigurationError("The experiment folder name must contain only letters, digits, ._-")
    if workspace.exists() and not workspace.is_dir():
        raise ConfigurationError(f"Experiment path is not a directory: {workspace}")
    if (workspace / "results").is_symlink():
        raise ConfigurationError("results/ must be a real directory, not a symlink")
    if not workspace.exists() or next(workspace.iterdir(), None) is None:
        return workspace

    settings = workspace / ".autoresearch.json"
    if settings.is_file() and not settings.is_symlink():
        try:
            saved = json.loads(settings.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            saved = None
        if (
            isinstance(saved, dict)
            and isinstance(saved.get("read_only"), list)
            and all(isinstance(path, str) and path for path in saved["read_only"])
        ):
            return workspace

    # Workspaces generated before saved selections have the same core layout.
    core_files = (
        workspace / "AGENTS.md",
        workspace / ".devcontainer/devcontainer.json",
    )
    if all(path.is_file() and not path.is_symlink() for path in core_files):
        try:
            container = json.loads(core_files[-1].read_text(encoding="utf-8"))
        except (ValueError, OSError):
            container = None
        if isinstance(container, dict) and container.get("workspaceFolder") == f"/workspace/{workspace.name}":
            return workspace
    raise ConfigurationError(
        f"Workspace is non-empty and is not an autoresearch directory: {workspace}. "
        "Choose a new/empty directory or an existing autoresearch workspace; "
        "--force does not bypass this check."
    )


def plan_read_only_mounts(
    workspace: Path, paths: Sequence[Path]
) -> tuple[ReadOnlyMount, ...]:
    """Resolve explicit selections and remove duplicates and covered descendants."""
    _validate_mount_path(workspace)
    workspace = Path(workspace).expanduser().resolve()
    _validate_mount_path(workspace)
    if workspace == Path(workspace.anchor):
        raise ConfigurationError("The workspace cannot be a filesystem root")
    if not workspace.parent.is_dir():
        raise ConfigurationError(f"Workspace parent does not exist: {workspace.parent}")
    sources: set[Path] = set()
    for path in paths:
        _validate_mount_path(path)
        source = Path(path).expanduser()
        if not source.is_absolute():
            source = workspace / source
        source = source.resolve()
        _validate_mount_path(source)
        if source == Path(source.anchor):
            raise ConfigurationError("A filesystem root cannot be selected")
        if not source.is_file() and not source.is_dir():
            raise ConfigurationError(f"Select an existing ordinary file or directory: {source}")
        sources.add(source)
    selected = sorted(
        (source for source in sources
         if not any(parent in sources and parent.is_dir() for parent in source.parents)),
        key=str,
    )
    base = Path(os.path.commonpath([
        workspace.parent,
        *(source if source.is_dir() else source.parent for source in selected),
    ]))
    mounts: list[ReadOnlyMount] = []
    for source in selected:
        suffix = source.relative_to(base).as_posix()
        target = "/project" if suffix == "." else f"/project/{suffix}"
        relative_source = os.path.relpath(source, workspace)
        _validate_mount_path(target)
        _validate_mount_path(relative_source)
        mounts.append(ReadOnlyMount(source, target, relative_source))
    return tuple(mounts)


@dataclass(frozen=True)
class GenerationResult:
    workspace: Path
    written: tuple[Path, ...]
    unchanged: tuple[Path, ...]
    removed: tuple[Path, ...] = ()


def generate(
    workspace: Path,
    *,
    read_only_paths: Sequence[Path] = (),
    gpus: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> GenerationResult:
    """Generate a workspace without exposing any unselected source paths."""
    workspace = validate_workspace(workspace)

    read_only_mounts = plan_read_only_mounts(workspace, read_only_paths)
    volume_suffix = hashlib.sha256(str(workspace).encode()).hexdigest()[:10]
    context = {
        "workspace_name": workspace.name,
        "volume_name": f"autoresearch-pi-{volume_suffix}",
        "read_only_mounts": read_only_mounts,
        "gpus": gpus,
        "settings_json": json.dumps(
            {"read_only": [mount.relative_source for mount in read_only_mounts], "gpus": gpus},
            ensure_ascii=False,
            indent=2,
        ),
        "mount_scaffolding": [
            {"target": mount.target, "directory": mount.source.is_dir()}
            for mount in read_only_mounts
        ],
    }

    env = Environment(undefined=StrictUndefined, keep_trailing_newline=True, autoescape=False)
    templates_dir = files("autoresearch_base").joinpath("templates")
    rendered: dict[Path, str] = {}
    unchanged: list[Path] = []
    removed: tuple[Path, ...] = ()
    old_pi_settings = workspace / ".pi/settings.json"
    if old_pi_settings.is_symlink() or not old_pi_settings.resolve().is_relative_to(workspace):
        raise ConfigurationError(f"Refusing to remove settings through a symlink: {old_pi_settings}")
    if old_pi_settings.exists():
        if not old_pi_settings.is_file():
            raise ConfigurationError(f"Expected an ordinary file: {old_pi_settings}")
        try:
            old_defaults = json.loads(old_pi_settings.read_text(encoding="utf-8"))
        except ValueError:
            old_defaults = None
        default_settings = json.loads(
            templates_dir.joinpath("pi_settings.json.j2").read_text(encoding="utf-8")
        )
        if old_defaults != default_settings and not force:
            raise ConfigurationError(
                f"Refusing to remove modified project Pi settings: {old_pi_settings}; "
                "review edits or rerun with --force to migrate to node-user settings"
            )
        removed = (old_pi_settings,)

    for obsolete_path in (
        "run-pi.sh",
        "experiments/run.sh",
        ".pi/extensions/research-tools.ts",
        ".pi/extensions/experiments.ts",
    ):
        obsolete = workspace / obsolete_path
        if obsolete.is_symlink() or not obsolete.resolve().is_relative_to(workspace):
            raise ConfigurationError(f"Refusing to remove obsolete file through a symlink: {obsolete}")
        if obsolete.exists():
            if not obsolete.is_file():
                raise ConfigurationError(f"Expected an ordinary file: {obsolete}")
            if not force:
                raise ConfigurationError(
                    f"Refusing to remove obsolete file without review: {obsolete}; "
                    "review edits or rerun with --force to use Pi's built-in tools"
                )
            removed += (obsolete,)

    for source, destination in TEMPLATES.items():
        target = workspace / destination
        if target.is_symlink() or not target.resolve().is_relative_to(workspace):
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
        if not (results_dir / ".gitkeep").exists():
            (results_dir / ".gitkeep").touch()
        for path in removed:
            path.unlink()

    return GenerationResult(workspace, tuple(rendered), tuple(unchanged), removed)
