import importlib.util
from pathlib import Path


PATH = Path(__file__).parents[2] / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/frame-methods/run_frame_methods.py"
SPEC = importlib.util.spec_from_file_location("frame_methods", PATH)
MODULE = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(MODULE)


def test_primary_candidate_uses_margin_then_recorded_rank():
    probe = {"candidates": [
        {"candidate_rank": 0, "fractional_margin": .02, "passed_fractional_margin_gate": False},
        {"candidate_rank": 5, "fractional_margin": .2, "passed_fractional_margin_gate": True},
        {"candidate_rank": 2, "fractional_margin": .2, "passed_fractional_margin_gate": True},
    ]}
    assert MODULE.primary_candidate(probe)["candidate_rank"] == 2


def test_primary_candidate_preserves_not_acquired():
    assert MODULE.primary_candidate({"candidates": []}) is None
