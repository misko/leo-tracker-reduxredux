"""Keep numerical workers on their qualified release when updating watchers."""

import sys
from pathlib import Path


def worker_command(module_file, worker_name, bulk_root, *, worker_root=None):
    root = (
        Path(module_file).resolve().parents[3]
        if worker_root is None
        else Path(worker_root).resolve(strict=True)
    )
    script = root / "tools" / worker_name
    if worker_root is not None and (not script.is_file() or not (root / "src").is_dir()):
        raise ValueError("Worker release must contain its numerical script and source package")
    command = [sys.executable, "-B", str(script), "--bulk-root", str(bulk_root)]
    if worker_root is not None:
        # The worker's imports must use the same frozen release as its script.
        # Inheriting the watcher's overlay would defeat that guarantee.
        command = ["/usr/bin/env", f"PYTHONPATH={root / 'src'}:{root / 'tools'}", *command]
    return command
