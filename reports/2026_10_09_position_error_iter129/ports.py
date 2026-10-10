"""Explicit immutable research ports; importing performs no recording access."""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def dependencies():
    folder = ROOT / "reports/2026_10_09_position_error_iter123"
    existing = sys.modules.get("retained_adapter")
    if existing is not None and Path(existing.__file__).resolve() != folder / "retained_adapter.py":
        raise ValueError("ambient retained-adapter collision")
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("continuation123_for129", folder / "run.py")
    continuation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(continuation)
    entry = continuation.load_search_entrypoint()
    import driver
    import retained_adapter

    return entry, driver, retained_adapter
