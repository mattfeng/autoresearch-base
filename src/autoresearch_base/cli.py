"""Command-line entry point for the autoresearch-base generator."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .generator import ConfigurationError, generate, plan_read_only_mounts, validate_workspace
from .picker import SelectionCancelled, pick_read_only_paths


def load_read_only_paths(workspace: Path) -> tuple[Path, ...] | None:
    configuration = workspace / ".autoresearch.json"
    if not configuration.exists():
        return None
    try:
        value = json.loads(configuration.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise ConfigurationError(f"Cannot read saved selection {configuration}: {error}") from error
    if (
        not isinstance(value, dict)
        or not isinstance(value.get("read_only"), list)
        or not all(isinstance(path, str) and path for path in value["read_only"])
    ):
        raise ConfigurationError(f"Expected a 'read_only' list of paths in {configuration}")
    return tuple((workspace / Path(path).expanduser()).resolve() for path in value["read_only"])


def _load_gpu_access(workspace: Path) -> bool:
    configuration = workspace / ".autoresearch.json"
    if not configuration.exists():
        return False
    try:
        value = json.loads(configuration.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        raise ConfigurationError(f"Cannot read saved configuration {configuration}: {error}") from error
    if not isinstance(value, dict) or not isinstance(value.get("gpus", False), bool):
        raise ConfigurationError(f"Expected a boolean 'gpus' value in {configuration}")
    return value.get("gpus", False)


def _prompt_gpu_access(default: bool) -> bool:
    choices = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"Give the devcontainer access to all NVIDIA GPUs? {choices} ").strip().lower()
        except (EOFError, KeyboardInterrupt) as error:
            raise SelectionCancelled from error
        if answer in {"cancel", "quit", "q"}:
            raise SelectionCancelled
        if not answer:
            return default
        if answer in {"y", "yes", "n", "no"}:
            return answer in {"y", "yes"}
        print("Enter yes or no, or cancel to leave without writing files.")


def _confirm_overwrite() -> None:
    while True:
        try:
            answer = input("Overwrite these generated files and remove listed obsolete files? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt) as error:
            raise SelectionCancelled from error
        if answer in {"", "n", "no", "cancel", "quit", "q"}:
            raise SelectionCancelled
        if answer in {"y", "yes"}:
            return
        print("Enter yes to overwrite, or no to leave without writing files.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="configure-autoresearch",
        description=(
            "Create a Pi experiment devcontainer with interactively selected "
            "read-only files and directories."
        ),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="new/empty experiment folder (browse from parent) or existing autoresearch workspace",
    )
    parser.add_argument(
        "--read-only",
        type=Path,
        action="append",
        metavar="PATH",
        help="include a file/directory without prompting; repeatable, relative to --workspace",
    )
    parser.add_argument(
        "--non-interactive",
        action="store_true",
        help="reuse saved .autoresearch.json selections without prompting",
    )
    parser.add_argument(
        "--gpus",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="enable/disable all NVIDIA GPUs; otherwise prompt or reuse the saved choice",
    )
    parser.add_argument("--force", action="store_true", help="replace changed generated files")
    parser.add_argument("--dry-run", action="store_true", help="show planned files without writing")
    args = parser.parse_args(argv)

    try:
        workspace = validate_workspace(args.workspace)
        if args.read_only is not None:
            selected = tuple(args.read_only)
        else:
            saved = load_read_only_paths(workspace)
            if args.non_interactive:
                if saved is None:
                    raise ConfigurationError(
                        "No saved selection; run interactively or supply --read-only PATH"
                    )
                selected = saved
            else:
                selected = pick_read_only_paths(workspace, saved or ())
        mounts = plan_read_only_mounts(workspace, selected)
        print("Read-only source mounts:")
        for mount in mounts:
            print(f"  {mount.source} -> {mount.target}")
        if not mounts:
            print("  None (the experiment workspace is mounted read/write)")
        if args.gpus is not None:
            gpus = args.gpus
        else:
            gpus = _load_gpu_access(workspace)
            if not args.non_interactive:
                gpus = _prompt_gpu_access(gpus)
        print(f"NVIDIA GPU access: {'enabled (--gpus=all)' if gpus else 'disabled'}")
        force = args.force
        if not force and not args.non_interactive:
            plan = generate(
                workspace, read_only_paths=selected, gpus=gpus, force=True, dry_run=True,
            )
            replacements = tuple(path for path in plan.written if path.exists())
            if not args.dry_run and (replacements or plan.removed):
                print("Existing autoresearch files will be replaced or removed; review local edits:")
                for path in replacements:
                    print(f"  OVERWRITE {path.relative_to(workspace)}")
                for path in plan.removed:
                    print(f"  REMOVE    {path.relative_to(workspace)}")
                _confirm_overwrite()
                force = True
            if args.dry_run:
                force = True
        result = generate(
            workspace, read_only_paths=selected, gpus=gpus, force=force, dry_run=args.dry_run,
        )
    except SelectionCancelled:
        print("\nSetup cancelled; no files written.")
        return 1
    except (ConfigurationError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")

    verb = "Would generate" if args.dry_run else "Generated"
    print(f"{verb} autoresearch workspace: {result.workspace}")
    for path in result.written:
        print(f"  {'PLAN' if args.dry_run else 'WRITE'} {path.relative_to(result.workspace)}")
    for path in result.unchanged:
        print(f"  KEEP  {path.relative_to(result.workspace)}")
    for path in result.removed:
        print(f"  {'PLAN REMOVE' if args.dry_run else 'REMOVE'} {path.relative_to(result.workspace)}")
    if not args.dry_run:
        print(f"Start the devcontainer, then run `pi` as node from /workspace/{result.workspace.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
