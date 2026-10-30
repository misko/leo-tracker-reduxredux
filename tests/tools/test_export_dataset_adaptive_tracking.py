import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "export_adaptive",
    Path(__file__).resolve().parents[2] / "tools/research/export_dataset_adaptive_tracking.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@dataclass
class Source:
    session_id: str = "session"
    input_manifest_sha256: str = "capture"
    analysis_manifest_sha256: str = "analysis"
    capture_mode: str = "adaptive"
    timing: object = None


def row():
    return dict(
        session_id="session",
        glrt_availability=dict(
            session_id="session",
            input_manifest_sha256="capture",
            analysis_manifest_sha256="analysis",
        ),
    )


def test_export_preserves_public_values():
    source = Source()
    assert MODULE.export_document(source, row()) == dict(
        session_id="session",
        input_manifest_sha256="capture",
        analysis_manifest_sha256="analysis",
        capture_mode="adaptive",
        timing=None,
    )


@pytest.mark.parametrize(
    "field", ["session_id", "input_manifest_sha256", "analysis_manifest_sha256", "capture_mode"]
)
def test_export_rejects_identity_or_analysis_drift(field):
    source = Source()
    setattr(source, field, "changed")
    with pytest.raises(ValueError):
        MODULE.export_document(source, row())
