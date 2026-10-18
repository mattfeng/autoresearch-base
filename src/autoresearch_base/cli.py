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
        result = generate(
            workspace, read_only_paths=selected, force=args.force, dry_run=args.dry_run,
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
