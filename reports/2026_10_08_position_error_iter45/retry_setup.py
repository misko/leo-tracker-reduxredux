"""Retry only recorded pre-fit storage-root failures, preserving first attempts."""

import json
import sys
from pathlib import Path

import complete_members

HERE = Path(__file__).resolve().parent


if __name__ == "__main__":
    for label in sys.argv[1:]:
        first = json.loads((HERE / "results" / f"{label}.json").read_text())
        assert first["status"] == "failed"
        assert first["error"] == (
            "ValueError('pinned storage root contains an inaccessible or symlink component: local')"
        )
        assert not (HERE / "baselines" / f"{label}.json").exists()
        complete_members.HERE = HERE / "retry"
        complete_members.run(label)
