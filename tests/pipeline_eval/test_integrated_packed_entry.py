from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import integrated_packed_member as member
from reports.ALGO08.v3 import legacy_block_raw_entry as legacy


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
