from copy import deepcopy
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / (
    "reports/ALGO08/single-core-2x/receiver_factor_ledger.py"
)
SPEC = spec_from_file_location("receiver_factor_ledger", SOURCE)
ledger_module = module_from_spec(SPEC)
SPEC.loader.exec_module(ledger_module)


def test_native_call_timing_is_paired_with_original_before_continuation_row():
    capture = ledger_module.FactorLedger()
    before = dict(visit_index=7, receiver_id=0, candidates=[{"candidate_rank": 0},
                                                           {"candidate_rank": 1}])
    call = ledger_module.NativeFactors(lambda: 2, capture)
    assert call() == 2
    capture.record(before)
    before["candidates"].pop()
    assert [factor["candidate_rank"] for factor in capture.rows[0]["candidates"]] == [0, 1]
    assert len(capture.native_cpu_ns) == 1 and capture.native_cpu_ns[0] > 0
    other = dict(visit_index=7, receiver_id=1, candidates=[])
    with pytest.raises(ValueError, match="not paired"):
        capture.record(other)
    with capture.span("native_factors"):
        pass
    capture.record(other)
    assert capture.rows[1] == other and len(capture.native_cpu_ns) == 2


def test_saved_authority_and_ordered_selection_are_both_required():
    capture = ledger_module.FactorLedger()
    for lane in (0, 1):
        with capture.span("native_factors"):
            pass
        capture.record(dict(visit_index=7, receiver_id=lane, candidates=[0, 1]))
    selected = [dict(row, candidates=[1]) for row in capture.rows]
    expected = dict(
        source=dict(session_id="saved", input_manifest_sha256="header",
                    raw_recording_authority_digest="raw", analysis_manifest_sha256="analysis",
                    probes=selected),
        provenance=dict(detector_sha256="detector", window_count=8, processed_windows=1,
                        excluded_windows=[]),
    )
    ledger_module.verify(deepcopy(expected), expected, capture)
    bad_authority = deepcopy(expected)
    bad_authority["source"]["raw_recording_authority_digest"] = "other"
    with pytest.raises(ValueError, match="raw_recording_authority_digest"):
        ledger_module.verify(bad_authority, expected, capture)
    bad_order = deepcopy(expected)
    bad_order["source"]["probes"].reverse()
    with pytest.raises(ValueError, match="probes"):
        ledger_module.verify(bad_order, expected, capture)
