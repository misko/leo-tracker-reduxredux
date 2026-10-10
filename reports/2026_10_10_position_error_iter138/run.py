"""Explicit namespace-repaired successor; reuse unchanged136 audit functions."""

import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = HERE.parent / "2026_10_10_position_error_iter136"


def isolated_implementation():
    """Resolve136 local imports without retaining generic names in sys.modules."""
    names = ("pair_score", "adapter", "audit_core")
    previous = {name: sys.modules.get(name) for name in names}
    try:
        for name in (*names, "run"):
            spec = importlib.util.spec_from_file_location(
                "audit136_for138_" + name, ORIGINAL / (name + ".py")
            )
            value = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(value)
            if name in names:
                sys.modules[name] = value
        return value
    finally:
        for name, old in previous.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


implementation = isolated_implementation()
implementation.HERE = HERE
sha = implementation.sha


def main():
    implementation.main()


if __name__ == "__main__":
    main()
