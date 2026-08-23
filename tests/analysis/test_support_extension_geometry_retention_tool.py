from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

_PATH = Path("tools/report_support_extension_geometry_retention.py")
_SPEC = importlib.util.spec_from_file_location("support_extension_geometry_retention_tool", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _track(label: str, points: int, rms: float) -> SimpleNamespace:
    return SimpleNamespace(
        label=label,
        trajectory=SimpleNamespace(point_count=points, residual_rms_hz=rms),
    )


def test_geometry_representative_uses_support_not_replay_outcome() -> None:
    chosen = _MODULE.geometry_representative(
        (_track("H4", 424, 100.0), _track("H5", 453, 120.0), _track("H6", 453, 120.0))
    )

    assert chosen.label == "H5"


def test_geometry_representative_breaks_equal_geometry_by_stable_label() -> None:
    chosen = _MODULE.geometry_representative(
        (_track("H9", 608, 89.9999999999), _track("H7", 608, 90.0))
    )

    assert chosen.label == "H7"
