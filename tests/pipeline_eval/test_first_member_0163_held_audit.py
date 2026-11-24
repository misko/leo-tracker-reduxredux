"""The selector replay comparison excludes only the fresh timing fields."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"))
from first_member_0163_held_audit import scientific_receipt


def test_preserves_held_policy_and_real_vs_prospective_refinement_counts():
    receipt = {"selector": {"cpu_s": 1}, "refinement_calls": 0, "would_refine_by_radio": {"0": 7, "1": 0},
               "choice": {"route": "unfiltered"}}
    assert scientific_receipt(receipt) == {"refinement_calls": 0, "would_refine_by_radio": {"0": 7, "1": 0},
                                          "choice": {"route": "unfiltered"}}
