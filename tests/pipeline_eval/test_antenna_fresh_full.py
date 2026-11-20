from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import antenna_fresh_full as trial
from tools.pipeline_eval.qualification import antenna_fresh_full_results as results
from tools.pipeline_eval.variants import partner_on_hit


def paired_rows():
    source = dict.fromkeys(
        (
            "session_id",
            "input_manifest_sha256",
            "raw_recording_authority_digest",
            "sample_rate_hz",
            "probe_ms",
            "radio_id",
            "stream_generation",
            "capture_mode",
        ),
        1,
    )
    source["analysis_manifest_sha256"] = "stock"
    source["probes"] = [
        dict(
            visit_index=visit, receiver_id=lane, candidates=[dict(passed_fractional_margin_gate=ok)]
        )
        for visit, lane, ok in ((0, 0, True), (0, 1, True), (1, 0, True), (1, 1, False))
    ]
    stock = dict(
        schema_version=2,
        clock_anchor=1,
        delivery_clocks=[10, 20],
        last_sample_counter=20,
        source=source,
        provenance={"excluded_windows": []},
    )
    schedule = [dict(visit=visit, selected_receiver=visit) for visit in range(2)]
    projected, _ = partner_on_hit.project(stock, schedule)
    return stock, projected, schedule


def test_live_gate_receipts_match_every_primary_and_use_only_true_gate():
    stock, projected, schedule = paired_rows()
    observed = [[0, 0, True], [1, 1, False]]
    witness = results.audit(stock, projected, schedule, observed)
    assert witness["full_projection_matches"]
    assert witness["actual_physical_receiver_calls"] == 3
    assert witness["dual_physical_receiver_calls"] == 4
    assert witness["covisible_partner_hits"] == witness["partner_only_hits"] == 1

    for not_observed in ([[0, 0, False], [1, 1, True]], [[0, 0, 1], [1, 1, False]]):
        with pytest.raises(ValueError, match="independently projected visit"):
            results.audit(stock, projected, schedule, not_observed)

    changed = deepcopy(projected)
    changed["source"]["probes"][3]["candidates"] = []
    assert not results.audit(stock, changed, schedule, observed)["full_projection_matches"]


def test_raw_and_numerical_reference_core_pairs_do_not_overlap():
    former = trial.whole.REPORT, trial.reference.REPORT, trial.reference.LANES
    with trial.context():
        assert trial.whole.REPORT == trial.reference.REPORT == trial.REPORT
        assert trial.whole.CPUS == {"DS26": [2, 3], "DS29": [4, 5]}
        assert set(trial.reference.LANES) == {22, 23}
        assert {r for roles in trial.reference.LANES.values() for r in roles} == set(trial.ROLES)
    assert former == (trial.whole.REPORT, trial.reference.REPORT, trial.reference.LANES)
