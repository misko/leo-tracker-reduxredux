from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import integrated_packed_member as member
from reports.ALGO08.v3 import legacy_block_raw_entry as legacy
from reports.ALGO08.v3.integrated_packed_cost import replace_acquisition, score


def test_packed_selection_reuses_scientific_flags_without_original_acquisition_modes():
    flags = [("--recording", "/prior"), ("--output", "/output"), ("--legacy-first-map-history", "/history.so"),
             ("--legacy-first-map-history-sha256", "pin"), ("--legacy-first-map-fast", "/solver-roster")]
    book = {"source": "/signed", "options": [x for pair in flags for x in pair] +
            ["--cairo-six-sheets", "--sparse8-primary", "--verify-original-once"]}
    old = member.arguments(book, "ordinary", Path("/ordinary"))
    new = member.arguments(book, "packed", Path("/packed"))
    assert "--verify-original-once" in old and "--strict-packed-eight" not in old
    assert "--verify-original-once" not in new and "--legacy-first-map-history" not in new
    assert "--strict-packed-eight" in new
    for key in ("--legacy-first-map-fast", "--sparse8-primary", "--cairo-six-sheets", "/signed"):
        assert key in old and key in new


def test_original_port_rejects_strict_and_mixed_input_modes():
    args = SimpleNamespace(history_risk_route=True, portable_orbit_index="/orbit", visit_frame_custody=None,
                           strict_packed_eight=True, cairo_residual_layout=False, cairo_six_sheets=True,
                           legacy_map_custody="/old-map", legacy_map_custody_sha256=None,
                           legacy_map_library=None, legacy_map_library_sha256=None)
    with pytest.raises(ValueError, match="original recording"):
        legacy.run(args, allow_cairo_orbits=True)
    with pytest.raises(ValueError, match="cannot use original block replay"):
        legacy.run(args, allow_cairo_orbits=True, allow_strict_packed=True)


def test_cost_replaces_acquisition_once_and_charges_prepared_setup():
    assert replace_acquisition(7., 3., 2., .1) == pytest.approx(6.1)
    with pytest.raises(ValueError):
        replace_acquisition(7., 8., 2., .1)


def test_sealed_cost_ledger_keeps_prepare_retrofit_and_owned_writer_distinct():
    result = score()
    row = result["modeled_integrated"]["positive_first"]
    ready = row["prepared_projection_positive_only"]
    conversion = result["historical_strict"]["conversion_and_readback_s"][0]
    assert row["existing_first_use_positive"]["summed_s"] == pytest.approx(ready["summed_s"] + conversion)
    writer = result["owned_0016"]["packed"]
    assert row["owned_write_to_exit_positive_projection"]["candidate_s"] == pytest.approx(
        ready["summed_s"] - row["observed_processes_s"][1] + writer["write_s"] + writer["independent_readback_s"])
    assert ready["remaining_to_half_s"] > 0
