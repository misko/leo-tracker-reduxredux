from pathlib import Path

import pytest

from reports.ALGO08.v3.continued_transfer_figure import measurements, read


def test_measured_elapsed_uses_the_correct_v3_scope_for_each_recording():
    base = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/measurements"
    cases = ("guarded-cfo-small-raw-0107", "continued-cfo-north", "named-final-0316")
    rows = measurements(*(read(base / f"{case}.json.gz") for case in cases))
    assert [named / current for _, _, named, current in rows] == pytest.approx((2.803, 1.493, 1.588), abs=.001)
    assert rows[-1][1].startswith("Saved v3 detections")
