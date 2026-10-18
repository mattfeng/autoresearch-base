"""Line-oriented filesystem picker for explicit read-only container inputs."""

from __future__ import annotations

import re
from pathlib import Path

from .generator import ConfigurationError, plan_read_only_mounts


class SelectionCancelled(Exception):
    """The user stopped setup before any files were written."""


def pick_read_only_paths(workspace: Path, initial: tuple[Path, ...] = ()) -> tuple[Path, ...]:
    workspace = workspace.expanduser().resolve()
    current = workspace
    if not workspace.exists() or next(workspace.iterdir(), None) is None:
        current = workspace.parent
    selected = {path.expanduser().resolve() for path in initial}
    entries: list[Path] = []

    def show_directory() -> None:
        nonlocal entries
        print(f"\nBrowsing: {current}")
        entries = sorted(current.iterdir(), key=lambda path: (not path.is_dir(), path.name.casefold()))
        if not entries:
            print("  (empty directory)")
        for index, path in enumerate(entries, start=1):
            mark = "x" if path.resolve() in selected else " "
            suffix = "/" if path.is_dir() else ""
            print(f"  [{mark}] {index:3}  {path.name}{suffix}")

    def resolve_choice(value: str) -> Path:
        if not value:
            raise ConfigurationError("Specify an entry number or a path; '.' means this directory")
        if value.isdecimal():
            index = int(value) - 1
            if not 0 <= index < len(entries):
                raise ConfigurationError("Entry number is out of range; use 'ls' to list entries")
            return entries[index].resolve()
        path = Path(value).expanduser()
        return (current / path).resolve() if not path.is_absolute() else path.resolve()

    def resolve_choices(value: str) -> set[Path]:
        if re.fullmatch(r"[0-9,\-\s]+", value):
            targets = set()
            for part in value.split(","):
                match = re.fullmatch(r"([0-9]+)(?:-([0-9]+))?", part)
                if match is None:
                    raise ConfigurationError("Use comma-separated numbers or ranges without spaces: 1,3-5")
                first = int(match[1])
                last = int(match[2]) if match[2] is not None else first
                if not 1 <= first <= last <= len(entries):
                    raise ConfigurationError(
                        f"Entry range {part!r} is invalid; choose ascending numbers from 1 to {len(entries)}"
                    )
                targets.update(entries[index - 1].resolve() for index in range(first, last + 1))
            return targets
        return {resolve_choice(value)}

    def show_selection() -> None:
        print("\nRead-only inputs (in addition to the experiment workspace):")
        try:
            mounts = plan_read_only_mounts(workspace, sorted(selected))
        except (ConfigurationError, OSError) as error:
            print(f"  Invalid selection: {error}")
            for path in sorted(selected):
                print(f"  {path}")
            print("  Use 'toggle PATH' to remove an invalid selection.")
            return
        if not mounts:
            print("  None. No parent repository is mounted automatically.")
        for mount in mounts:
            print(f"  {mount.source} -> {mount.target}")
        print("  Selecting a directory includes all of its descendants.")

    print("Choose files/directories to expose read-only to the experiment container.")
    print("Commands: ls | up | cd NAME/NUMBER/PATH | toggle NUMBERS/PATH | select NUMBERS/PATH")
    print("          1,3,5-8 toggles entries; ranges are inclusive, no spaces in number lists")
    print("          select . | selected | done | cancel   (paths may contain spaces)")
    show_directory()
    if selected:
        show_selection()
    while True:
        try:
            line = input("sources> ").strip()
        except (EOFError, KeyboardInterrupt) as error:
            raise SelectionCancelled from error
        command, _, argument = line.partition(" ")
        argument = argument.strip()
        try:
            if re.fullmatch(r"[0-9,\-]+", line):
                command, argument = "toggle", line
            if command in {"cancel", "quit", "q"}:
                raise SelectionCancelled
            if command == "done":
                show_selection()
                return tuple(mount.source for mount in plan_read_only_mounts(workspace, sorted(selected)))
            if command in {"", "ls", "help"}:
                if command == "help":
                    print("Browse with 'up'/'cd'; select files or whole directories with 'toggle'.")
                    print("Enter '1,3-5' to toggle a batch, or 'select 1,3-5' to only add entries.")
                    print("Use 'select .' for the current directory, 'selected' to review, 'done' to finish.")
                show_directory()
            elif command in {"up", "cd"}:
                target = current.parent if command == "up" else resolve_choice(argument)
                if not target.is_dir():
                    raise ConfigurationError(f"Not a directory: {target}")
                # Check readability before changing the current location.
                list(target.iterdir())
                current = target
                show_directory()
            elif command in {"toggle", "select"}:
                targets = resolve_choices(argument)
                additions = targets - selected if command == "toggle" else targets
                # Validate every addition before changing anything in this batch.
                plan_read_only_mounts(workspace, sorted(additions))
                if command == "toggle":
                    selected.symmetric_difference_update(targets)
                else:
                    selected.update(targets)
                show_selection()
                show_directory()
            elif command == "selected":
                show_selection()
            else:
                print("Unknown command. Use 'help', or 'cancel' to leave without writing files.")
        except (ConfigurationError, OSError) as error:
            print(f"Cannot select or browse: {error}")
