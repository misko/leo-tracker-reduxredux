import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "report_post_ds24",
    Path(__file__).resolve().parents[2] / "tools/research/report_post_ds24_dataset.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_unavailable_incomplete_acquisition_remains_in_every_count():
    row = dict(
        case_id="case",
        dataset_label="DS26-0001",
        raw_identity_sha256="raw",
        mode="fast",
        captured_utc_ns=1792852694000000000,
        recording_state="incomplete",
        glrt_availability=dict(available=False),
    )
    daily, readiness = MODULE.describe(dict(counts=dict(members=1), members=[row]))
    assert daily["2026-10-24", "fast"] == 1
    assert readiness["fast", False] == 1


def test_figure_denominator_must_match_manifest_count():
    with pytest.raises(ValueError, match="count differs"):
        MODULE.describe(dict(counts=dict(members=1), members=[]))
