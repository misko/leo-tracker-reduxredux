"""The scoped replay carries the exact original offer and compiled receiver."""

from pathlib import Path
import sys

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from first_member_0163_acquisition import enrolled_options


def test_enrollment_keeps_sparse_original_route_and_only_rebinds_local_authority():
    command = ["--archive", "prior", "--archive-sha256", "prior-digest", "--region", "prior-offer",
               "--sparse8-primary", "--verify-original-once"]
    archive = {"root": "original-stage", "snapshots_sha256": "signed-causal"}
    assert enrolled_options(command, "same-offer", archive) == [
        "--archive", "original-stage", "--archive-sha256", "signed-causal", "--region", "same-offer",
        "--sparse8-primary", "--verify-original-once",
    ]
    assert "prior-offer" in command
    with pytest.raises(ValueError, match="verified once"):
        enrolled_options(command[:-1], "same-offer", archive)
