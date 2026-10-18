"""Device ownership controls node's supplementary groups, not a fixed host GID."""

from importlib.resources import files
import runpy
import stat
from types import SimpleNamespace


helper = runpy.run_path(str(files("autoresearch_base").joinpath("templates/devcontainer/init-gpu.py.j2")))


def test_only_group_restricted_character_devices_require_membership():
    modes = [
        (stat.S_IFCHR | 0o660, 1002),
        (stat.S_IFCHR | 0o660, 44),
        (stat.S_IFCHR | 0o640, 1003),
        (stat.S_IFCHR | 0o620, 1004),
        (stat.S_IFCHR | 0o664, 1005),
        (stat.S_IFCHR | 0o644, 1006),
        (stat.S_IFCHR | 0o666, 0),
        (stat.S_IFDIR | 0o750, 0),
        (stat.S_IFREG | 0o660, 99),
    ]
    devices = [SimpleNamespace(stat=lambda mode=mode, gid=gid: SimpleNamespace(st_mode=mode, st_gid=gid)) for mode, gid in modes]
    dev = SimpleNamespace(glob=lambda pattern: devices)
    assert helper["device_group_ids"](dev) == {44, 1002, 1003, 1004, 1005}


def test_membership_reuses_numeric_gid_preserves_members_and_is_idempotent(tmp_path):
    group_file = tmp_path / "group"
    group_file.write_text("root:x:0:\nnode:x:1000:\nvideo:x:44:alice\nautoresearch-gpu-1002:x:77:bob\n")
    group_file.chmod(0o640)
    helper["grant_device_groups"](group_file, {44, 1002})
    assert group_file.read_text() == (
        "root:x:0:\nnode:x:1000:\nvideo:x:44:alice,node\n"
        "autoresearch-gpu-1002:x:77:bob\nautoresearch-gpu-1002-device:x:1002:node\n"
    )
    assert stat.S_IMODE(group_file.stat().st_mode) == 0o640
    before = group_file.stat().st_mtime_ns
    helper["grant_device_groups"](group_file, {44, 1002})
    assert group_file.stat().st_mtime_ns == before


def test_without_restricted_gpu_devices_group_database_is_untouched(tmp_path):
    group_file = tmp_path / "group"
    group_file.write_text("node:x:1000:\n")
    before = group_file.stat().st_mtime_ns
    helper["grant_device_groups"](group_file, set())
    assert group_file.read_text() == "node:x:1000:\n"
    assert group_file.stat().st_mtime_ns == before
