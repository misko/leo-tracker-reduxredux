import pytest

from reports.ALGO08.v3.legacy_frame_figure import (
    ALL, FIVE, FIX_WRITER, HERE, SHORT_ORIGINAL, SHORT_WRITER, load_seal, timings, writer_pair,
)


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


def test_writer_bars_use_the_two_matched_children_and_preserve_the_old_clocks():
    base = HERE / "measurements"
    fix = load_seal(base / "legacy-map-writer-0016.json.gz", FIX_WRITER)
    short = load_seal(base / "lightweight-audit-0107.json.gz", SHORT_WRITER)
    original = load_seal(base / "legacy-block-all-0107.json.gz", SHORT_ORIGINAL)
    positive, withholding = writer_pair(fix, short, original)
    assert positive == pytest.approx([10.744677, 7.092842, 7.359185], abs=1e-6)
    assert withholding == pytest.approx([1.497018, .966520, .535740], abs=1e-6)
    short["prior_all_member"]["elapsed_s"] += .01
    with pytest.raises(ValueError, match="matched cohort"):
        writer_pair(fix, short, original)
