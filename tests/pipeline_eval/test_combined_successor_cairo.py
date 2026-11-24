from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3.combined_successor_cairo_trial import ENTRY, allowed_tiny, cairo_command, modeled_gates
from reports.ALGO08.v3.legacy_block_raw_entry import orbit_renderer


@pytest.mark.parametrize(("cairo", "ordinary", "allow", "expected"), (
    (False, True, False, False), (False, True, True, False), (True, False, True, True),
    (True, False, False, None), (True, True, True, None), (False, False, True, None)))
def test_explicit_cairo_permission_preserves_original_mode(cairo, ordinary, allow, expected):
    args = SimpleNamespace(cairo_six_sheets=cairo, cairo_residual_layout=ordinary)
    if expected is None:
        with pytest.raises(ValueError, match="admitted standard"):
            orbit_renderer(args, allow_cairo_orbits=allow)
    else:
        assert orbit_renderer(args, allow_cairo_orbits=allow) is expected


def test_normal_original_command_only_changes_renderer_and_output():
    original = ["/usr/bin/timeout", "--kill-after=2s", "75s", "python", "-IB", "/tmp/legacy_first_map_entry.py",
                "--verify-original-once", "--legacy-first-map-fast", "/tmp/binding.json", "--history-risk-route",
                "--cairo-residual-layout", "--recording", "/physical", "--output", "/old"]
    expected = list(original)
    expected[5], expected[original.index("--cairo-residual-layout")], expected[-1] = str(ENTRY), "--cairo-six-sheets", "/fresh"
    assert cairo_command(original, Path("/fresh")) == expected


@pytest.mark.parametrize(("wall", "qualified", "allowed"), ((6.99, True, True), (7.06, True, False), (6.99, False, False)))
def test_withhold_requires_qualified_positive_and_modeled_cohort_gate(wall, qualified, allowed):
    def runtime(seconds):
        return {"elapsed_s": seconds, "cpu_s": seconds}

    prior = {"DS30-0016": {"installed": runtime(10.744677)},
             "DS30-0107": {"installed": runtime(1.497018), "process": runtime(.601460)}}
    process = runtime(wall) | {"exit_code": 0}
    positive = {"qualified": qualified, "modeled_cohort_gates": modeled_gates(process, prior)}
    assert allowed_tiny(positive, process) is allowed
