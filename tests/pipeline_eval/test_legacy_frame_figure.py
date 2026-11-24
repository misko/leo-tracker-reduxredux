import pytest

from reports.ALGO08.v3.legacy_frame_figure import ALL, FIVE, HERE, load_seal, timings


def test_complete_recording_shares_control_and_charges_both_preparation_steps():
    base = HERE / "measurements"
    first = load_seal(base / "legacy-block-raw-0016.json.gz", FIVE)
    complete = load_seal(base / "legacy-block-all-0016.json.gz", ALL)
    rows = timings(first, complete)
    assert [row[1] for row in rows] == pytest.approx([10.744677, 8.629779, 7.580689, 7.092842], abs=1e-6)
    assert rows[-1][1] + rows[-1][2] == pytest.approx(11.993402, abs=1e-6)
    complete["checks"]["all_figures"] = False
    with pytest.raises(ValueError, match="fully scored"):
        timings(first, complete)
