from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
import conditional_repair_census as census


def test_reasons_match_archived_gate_fields_only():
    document = b'''{"text": "repair_original_joint_pair_gate",
                    "reason": "repair_rejection_cap",
                    "original": {"reason":"repair_original_joint_pair_gate"}}'''
    assert census.reason_mentions(document) == {census.JOINT_REFUSAL: 1, census.CAP_REFUSAL: 1}


def test_early_repair_refusal_cannot_supply_post_repair_calibrations():
    attempt = {"decision": "fallback", "reason": census.CAP_REFUSAL, "pair_passes": False,
               "repair": {"status": "rejected", "reason": census.CAP_REFUSAL, "attempted_refits": 0,
                          "rejection_counts": {"tracks": [63, 5]}}}
    assert census.attempt_evidence(attempt)["repair"]["finish"] is None


def test_census_ignores_successful_and_unlabelled_repairs():
    docs = {"files": [
        {"case_hint": "DS30-0004", "path": "cap", "attempts": [{"repair": {"status": "rejected"}}]},
        {"case_hint": "DS30-0169", "path": "accepted", "attempts": [{"repair": {"status": "complete"}}]},
        {"case_hint": None, "path": "simulation", "attempts": [{"repair": {"status": "rejected"}}]},
    ]}
    assert [case for case, _path, _attempt in census.physical_refusals(docs)] == ["DS30-0004"]
    assert census.case_hint(Path("leo-v3-combined-0173-blind01/routed/risk-route.json")) == "DS30-0173"
    assert census.case_hint(Path("leo-v3-north/risk-route.json")) is None
