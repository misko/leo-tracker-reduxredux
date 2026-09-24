from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).with_name("enqueue_frozen.py")
_SPEC = importlib.util.spec_from_file_location("ds2_enqueue", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(MODULE)


def _row(index: int) -> dict[str, object]:
    return {
        "session_id": f"scan-fw-{index:016x}",
        "inclusion": {"raw_capture_eligible": True},
    }


def test_frozen_scans_requires_exactly_twenty_unique_eligible_rows() -> None:
    document = {"schema": "ds2-adaptive-inventory/v1", "scans": [_row(i) for i in range(20)]}
    assert len(MODULE.frozen_scans(document)) == 20


def test_frozen_scans_rejects_drift() -> None:
    document = {"schema": "ds2-adaptive-inventory/v1", "scans": [_row(i) for i in range(19)]}
    with pytest.raises(ValueError, match="exactly 20"):
        MODULE.frozen_scans(document)


def test_geometry_summary_does_not_create_a_binding_when_it_is_absent() -> None:
    class Manifest:
        receiver_geometry = None

    class Capture:
        manifest = Manifest()

    assert MODULE.geometry_summary(Capture()) == {"status": "absent_from_capture_manifest"}


def test_registry_path_is_the_explicit_station_authority() -> None:
    assert MODULE.GEOMETRY_REGISTRY.name == "gauss-r21-lt3d-001a-20260920-v1.json"
    assert MODULE.GEOMETRY_REGISTRY.is_file()
