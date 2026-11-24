from pathlib import Path

import pytest

from reports.ALGO08.v3.nomination_handoff_south import staged
from reports.ALGO08.v3.nomination_handoff_south_score import decision


def test_ram_path_admission_accepts_both_mounts_without_enabling_backing_paths():
    for root in (Path("/tmp"), Path("/dev/shm")):
        assert staged(root) == root
    with pytest.raises(ValueError, match="tmpfs"):
        staged(Path("/var/tmp"))


def test_mirror_does_not_call_a_complete_omission_a_fix():
    assert decision("complete", False) == "false_fix"
    assert decision("withheld", False) == "withheld"
    assert decision("complete", True) == "fix"
    assert decision("withheld", True) == "false_withhold"
    with pytest.raises(ValueError):
        decision("failed", False)
