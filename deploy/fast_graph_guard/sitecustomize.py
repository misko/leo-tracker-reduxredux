"""Per-process read receipts: production inference can read only its own data."""

import atexit
from contextvars import ContextVar
import json
import os
from pathlib import Path
import sys

root = Path(os.environ["LEO_FAST_GRAPH_RUN_ROOT"]).resolve()
source = Path(os.environ["LEO_FAST_GRAPH_INPUT"]).resolve()
archive = Path(os.environ["LEO_FAST_GRAPH_TLE_ROOT"]).resolve()
release = Path(os.environ["LEO_FAST_GRAPH_SOURCE_ROOT"]).resolve()
reads, denied = set(), set()
python_spawns = []
fd_target = ContextVar("fast_graph_fd_target", default=None)
original_open = os.open


def confined_open(path, flags, mode=0o777, *, dir_fd=None):
    # CPython's open audit event omits dir_fd. Preserve the actual target of
    # descriptor-relative public archive reads rather than guessing from cwd.
    target = None
    if dir_fd is not None:
        target = Path(os.readlink(f"/proc/self/fd/{dir_fd}")) / os.fsdecode(path)
    token = fd_target.set(target)
    try:
        return original_open(path, flags, mode, dir_fd=dir_fd)
    finally:
        fd_target.reset(token)


def audit(event, args):
    if event == "subprocess.Popen":
        executable = Path(os.fsdecode(args[0])).resolve()
        if executable == Path(sys.executable).resolve():
            python_spawns.append(str(executable))
        return
    if event != "open" or not isinstance(args[0], (str, bytes, os.PathLike)):
        return
    path, mode, flags = args
    if flags & os.O_DIRECTORY:
        return  # Directory traversal exposes metadata, not file contents.
    reading = ("r" in mode or "+" in mode) if mode is not None else flags & os.O_ACCMODE != os.O_WRONLY
    if not reading:
        return
    path = Path(fd_target.get() or os.fsdecode(path)).resolve()
    if path.is_relative_to(archive):
        reads.add(str(path))
        return
    if path.is_relative_to("/mnt/qnap01"):
        denied.add(str(path))
        raise PermissionError("Graph inference does not read QNAP")
    if path == source or path.is_relative_to(root):
        reads.add(str(path))
        return
    code = any(path.is_relative_to(release / folder) for folder in ("src", "tools", "deploy/fast_graph_guard")) and path.suffix in {".py", ".pyc", ".so"}
    if code or path == release / "deploy/config/fast-graph-tracklets-v1.json":
        return
    dependencies = (Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve())
    if any(path.is_relative_to(p) for p in dependencies):
        return
    system_roots = ("/usr", "/lib", "/lib64", "/proc", "/sys", "/etc/fonts")
    if any(path.is_relative_to(p) for p in system_roots) or str(path) in {"/etc/localtime", "/etc/timezone", "/dev/null", "/dev/urandom"}:
        return
    denied.add(str(path))
    raise PermissionError("Graph inference attempted an unrelated data read: " + str(path))


def receipt():
    folder = root / "read_receipts"
    folder.mkdir(exist_ok=True)
    path = folder / (str(os.getpid()) + ".json")
    path.write_text(json.dumps(dict(pid=os.getpid(), parent_pid=os.getppid(),
            python_spawns=python_spawns, read_paths=sorted(reads), denied_paths=sorted(denied)), indent=2) + "\n")


sys.addaudithook(audit)
os.open = confined_open
atexit.register(receipt)
