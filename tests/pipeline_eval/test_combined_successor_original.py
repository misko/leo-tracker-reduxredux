from pathlib import Path

import pytest

from reports.ALGO08.v3.combined_successor_original import allowed_tiny, command_for, PORT


COMMAND = [
    "/usr/bin/timeout", "--kill-after=2s", "75s", "python", "-IB", "/some/tree/legacy_first_map_entry.py",
    "--verify-original-once", "--legacy-first-map-fast", "/tmp/artifacts.json", "--history-risk-route",
    "--cairo-residual-layout", "--recording", "/physical", "--output", "/old",
]


def test_command_changes_only_successor_entry_and_fresh_output():
    result = command_for(COMMAND, Path("/new"))
    assert result[5] == str(PORT)
    assert result[-1] == "/new"
    assert result[:5] == COMMAND[:5] and result[6:-1] == COMMAND[6:-1]
    assert COMMAND[-1] == "/old"


@pytest.mark.parametrize("flag", ("--legacy-first-map-replay", "--cairo-six-sheets", "--strict-packed-eight"))
def test_command_rejects_unmatched_receiver_or_publisher(flag):
    with pytest.raises(ValueError, match="identical original"):
        command_for([*COMMAND, flag], Path("/new"))


@pytest.mark.parametrize(("qualified", "code", "wall", "allowed"), (
    (True, 0, 8.04, True), (True, 0, 8.05, False), (True, 0, 8.048, False), (False, 0, 7., False), (True, 1, 7., False)))
def test_contingent_withhold_requires_qualified_strictly_faster_fix(qualified, code, wall, allowed):
    accepted = {"qualified": qualified, "verified_once": {"elapsed_s": 8.048}}
    assert allowed_tiny(accepted, {"elapsed_s": wall, "exit_code": code}) is allowed
