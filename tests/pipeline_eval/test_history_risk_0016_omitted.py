from pathlib import Path

import pytest

from reports.ALGO08.v3 import history_risk_0016_omitted as omitted


def test_command_changes_only_the_two_geographic_output_arguments(tmp_path):
    old = ["/usr/bin/timeout", "--kill-after=2s", "45s", "/opt/leo/python", "-IB", "/source/exact_named_raw.py",
           "--recording", "/signed/recording", "--archive", "/signed/causal", "--archive-sha256", "test",
           "--region", "/signed/containing", "--output", "/sealed/containing", "--history-risk-route", "--cairo-six-sheets"]
    path, output = tmp_path/"offer.json", tmp_path/"new"
    actual = omitted.changed_arguments(old, path, output)
    expected = old[6:].copy()
    expected[expected.index("--region")+1] = str(path)
    expected[expected.index("--output")+1] = str(output)
    assert actual == expected
    with pytest.raises(ValueError, match="qualified ordinary-input"):
        omitted.changed_arguments(old+["--strict-packed-eight"], path, output)


def test_east_omission_retains_the_original_screen_offset_and_width():
    original = dict(center=[37.906, -122.545], screen_center=[37.5, -122.0], width_km=25.0)
    assert omitted.translated_offer(original) == dict(center=[37.906, -120.545], screen_center=[37.5, -120.0], width_km=25.0)
    assert original["center"] == [37.906, -122.545]


def test_ordered_owner_comparison_distinguishes_switches_and_losses():
    controls = [["first", 101, "conditional"], ["second", 102, "predictive"]]
    shifted = [["first", 103, "conditional"], ["third", 103, "conditional"]]
    result = omitted.summarise_owners({key: controls for key in omitted.ARMS}, {key: shifted for key in omitted.ARMS})
    assert result["c0"]["reassigned_norad"] == 1
    assert result["fitted_c"]["dropped"] == ["second"]
    assert result["c0"]["added"] == ["third"]
