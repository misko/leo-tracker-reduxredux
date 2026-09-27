from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
CONTROL = HERE.parents[2] / "reports/2026_09_26_ds5_server_eval/dataset"
sys.path.insert(0, str(HERE))

from build import build, sha256  # noqa: E402
from phase_cfo import NativePhaseCFO  # noqa: E402
from run_experiment import fallback_reason, load_inputs  # noqa: E402


def test_build_receipt_and_frozen_inventory() -> None:
    library = build()
    receipt = json.loads(library.with_name(library.name + ".build.json").read_text())
    assert sha256(library) == receipt["binary_sha256"]
    for source, expected in receipt["sources_sha256"].items():
        assert sha256(Path(source)) == expected
    development, controls = load_inputs()
    assert len(development) == 128
    assert len(controls) == 12
    assert all(case["split"] == "dev" for case in development)
    assert {case["truth"]["kind"] for case in controls} == {"pilot", "noise", "tone"}


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
def test_constructed_pilot_is_deterministic_and_input_is_immutable(rate: int) -> None:
    payload = json.loads((CONTROL / "cases.json").read_text())
    case = next(
        case for case in payload["cases"]
        if case["split"] == "control" and case["rate_hz"] == rate
        and case["truth"]["kind"] == "pilot"
    )
    iq = np.load(CONTROL / case["raw_npy"]["path"], allow_pickle=False, mmap_mode="r")
    before = hashlib.sha256(iq).hexdigest()
    with NativePhaseCFO(rate, case["edge"]) as engine:
        rows = [engine.run(iq[:, 0, :], maximum=1, seeded=False) for _ in range(3)]
        signatures = []
        for result in rows:
            confirmation = result.confirmations[0]
            assert confirmation.candidate_count == 1
            candidate = confirmation.candidates[0]
            assert candidate.fractional_complete
            assert candidate.margin > 0.025
            assert -400_000 <= candidate.acquired_cfo_hz <= 400_000
            signatures.append((candidate.epoch, candidate.fractional_offset_samples,
                               candidate.acquired_cfo_hz, candidate.exact_score,
                               candidate.control_score))
        assert signatures[1:] == signatures[:1] * 2
        profile = engine.profile()
        assert profile["acquisition_fft_cpu_ms"] >= 0
        assert profile["conditioned_cpu_ms"] > 0
    assert hashlib.sha256(iq).hexdigest() == before


def test_fallback_policy_is_only_structural_failure() -> None:
    class Candidate:
        def __init__(self, complete):
            self.fractional_complete = complete

    class Confirmation:
        def __init__(self, candidates):
            self.candidate_count = len(candidates)
            self.candidates = candidates

    class Result:
        def __init__(self, candidates):
            self.confirmations = [Confirmation(candidates)]

    assert fallback_reason(Result([])) == "no_candidate"
    assert fallback_reason(Result([Candidate(False)])) == "fractional_incomplete"
    assert fallback_reason(Result([Candidate(True)])) is None


def test_frozen_result_is_development_only_and_records_rejection() -> None:
    path = HERE / "results.json"
    assert sha256(path) == "d502c8bc1968f3e6fe246c25ff177a51e74d5bc4aeef5f972c1e4bdc87ef36d0"
    result = json.loads(path.read_text())
    assert result["fresh_holdout_opened"] is False
    assert result["gates"]["passed"] is False
    assert result["summary"]["all"]["receiver_visits"] == 256
    assert result["summary"]["all"]["matched_reference_positives"] == 31
    assert len(result["control_rows"]) == 24
    assert result["control_decision_changes"] == 0
