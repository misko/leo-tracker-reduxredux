from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("eight_ms_south_transfer")


def test_only_original_site_and_checkout_change_in_command(trial):
    old = ["timeout", "--kill-after=2s", "90s", "python", "-IB", "/other/combined_raw_research.py",
           "--eight-ms-native-history", "--catalogue-block-rank", "--recording", "north", "--archive", "old-archive",
           "--region", "old-offer", "--output", "old-output", "--short-binary", "signed-8ms.so"]
    north = {"command": old}
    south = dict(recording="south", archive={"root": "archive"}, offers={"containing": "south-offer"})
    command = trial.command_for(north, south, "south-output")
    assert command[6:9] == old[6:9]
    assert command[9:] == ["south", "--archive", "archive", "--region", "south-offer",
                          "--output", "south-output", "--short-binary", "signed-8ms.so"]
    with pytest.raises(ValueError, match="two-scan"):
        trial.command_for({"command": [*old, "--full-anchor-primary-library"]}, south, "out")


@pytest.mark.parametrize(("face", "decision", "result"), [
    (.1, "complete", "valid_fix"), (.1, "withheld", "false_withhold"),
    (-.1, "complete", "false_fix"), (-.1, "withheld", "valid_withhold"),
])
def test_original_omitted_fix_is_a_geographic_failure(trial, face, decision, result):
    assert trial.geographic_status(face, decision) == result
