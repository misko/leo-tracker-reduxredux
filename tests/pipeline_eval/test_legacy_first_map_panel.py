from pathlib import Path
from sys import path
from unittest.mock import patch

import pytest

from reports.ALGO08.v3 import legacy_first_map_input as first


def command_module():
    here = Path(first.__file__).parent
    with patch("sys.path", [str(here), *path]):
        from reports.ALGO08.v3 import legacy_first_map_panel
    return legacy_first_map_panel


def test_original_command_cannot_consume_a_prior_plan(tmp_path):
    panel = command_module()
    flags = ["--recording", "old-recording", "--archive", "old-archive", "--region", "old-offer",
             "--archive-sha256", "old-pin", "--output", "old-output", "--legacy-first-map-plan",
             "prior-custody", "--legacy-first-map-plan-sha256", "prior-pin", "--history-risk-route",
             "--cairo-residual-layout", "--legacy-first-map-history", "history.so",
             "--legacy-first-map-replay", "replay.so"]
    command = ["timeout", "--kill-after=2s", "75s", "python", "-IB", panel.ENTRY, *flags]
    scoped = [value.replace("old-", "new-") for value in flags[:8]]
    output = tmp_path / "output"
    updated = panel.command_for(command, scoped, output)
    assert updated[6:14] == scoped
    assert updated[15] == str(output)
    assert updated[16:] == flags[14:]
    assert "prior-custody" in command
    with pytest.raises(ValueError, match="original input"):
        panel.command_for([*command, "--legacy-map-custody", "an-existing-map"], scoped, output)
