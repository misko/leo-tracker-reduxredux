from pathlib import Path

import pytest

from reports.ALGO08.v3.legacy_first_map_north import archived, command_for, controls, LIBRARIES


def frozen():
    north, *_ = controls()
    ordinary = archived("legacy-first-use-original-panel")
    return ordinary["admission"]["commands"]["DS30-0016"], north


def test_normal_first_use_command_uses_original_north_offer_and_full_receiver(tmp_path):
    template, north = frozen()
    output = tmp_path / "run"
    command = command_for(template, north, output)
    assert Path(command[5]).name == "legacy_first_map_entry.py"
    for flag, value in (
        ("--recording", north["request"]["recording"]),
        ("--archive", north["request"]["archive"]["root"]),
        ("--region", north["request"]["inside_offer"]),
        ("--archive-sha256", north["request"]["archive"]["snapshots_sha256"]),
        ("--output", str(output)),
    ):
        assert command[command.index(flag) + 1] == value
    assert "--history-risk-route" in command
    assert "--cairo-residual-layout" in command
    assert "--cairo-six-sheets" not in command
    assert "--research-adaptive-position-map" not in command


@pytest.mark.parametrize("foreign", ["--legacy-first-map-plan", "--legacy-map-custody", "--strict-packed-eight"])
def test_fresh_candidate_rejects_foreign_map_priors(tmp_path, foreign):
    template, north = frozen()
    with pytest.raises(ValueError, match="no-plan"):
        command_for([*template, foreign], north, tmp_path)


def test_recipe_library_replacement_is_rejected(tmp_path):
    template, north = frozen()
    template[template.index(LIBRARIES[0]) + 1] = "/different-receiver.so"
    with pytest.raises(ValueError, match="library differs"):
        command_for(template, north, tmp_path)
