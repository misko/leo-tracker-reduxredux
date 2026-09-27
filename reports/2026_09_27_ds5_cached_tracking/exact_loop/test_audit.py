from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from audit import run  # noqa: E402


def test_pinned_audit_finds_existing_exact_arm_paths_and_rejects_pack():
    result = run()
    assert result["decision"] == "stop-before-implementation"
    assert result["projection_context"].startswith("historical x86_64 server")
    assert any("ARM packing cost remains unknown" in item for item in result["limitations"])
    assert set(result["projection_by_rate"]) == {"2500000", "5000000"}
    assert all(not row["projection_gate_passed"] for row in result["projection_by_rate"].values())
    assert all(row["perfect_removal_fraction_of_gate"] < 1.0
               for row in result["projection_by_rate"].values())
    assert "vmull.s16" in result["existing_arm_exact_paths"]["rank_disassembly_crosscheck_only"].values()


def test_saved_evidence_matches_live_audit():
    saved = json.loads((HERE / "evidence.json").read_text())
    assert saved == run()
