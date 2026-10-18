"""Command-line entry point for the autoresearch-base generator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .generator import ConfigurationError, generate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="configure-autoresearch",
        description=(
            "Create a separate, read-only Pi experiment devcontainer in a child "
            "directory of an existing repository."
        ),
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="experiment folder (default: current directory); parent is the project repository",
    )
    parser.add_argument("--force", action="store_true", help="replace changed generated files")
    parser.add_argument("--dry-run", action="store_true", help="show planned files without writing")
    args = parser.parse_args(argv)

    try:
        result = generate(args.workspace, force=args.force, dry_run=args.dry_run)
    except (ConfigurationError, OSError) as exc:
        parser.exit(2, f"error: {exc}\n")

    verb = "Would generate" if args.dry_run else "Generated"
    print(f"{verb} autoresearch workspace: {result.workspace}")
    for path in result.written:
        print(f"  {'PLAN' if args.dry_run else 'WRITE'} {path.relative_to(result.workspace)}")
    for path in result.unchanged:
        print(f"  KEEP  {path.relative_to(result.workspace)}")
    if not args.dry_run:
        print("Open this folder in a separate Dev Containers window and use ./run-pi.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
