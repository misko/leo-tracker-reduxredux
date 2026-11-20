import json

import pytest

from tools.pipeline_eval.qualification import coarse_waveform as trial
from tools.pipeline_eval.qualification import coarse_waveform_results as results
from tools.pipeline_eval.qualification.full_v5_check import ALIAS_HZ


def test_retry_work_counts_separate_logical_retries_from_guarded_repeats():
    primary, retry = 104286, 191037
    grid = [
        dict(calls=0, inverse_ffts=0),
        dict(calls=2, inverse_ffts=2 * primary),
        dict(calls=3, inverse_ffts=2 * primary + retry),
        dict(calls=5, inverse_ffts=3 * primary + 2 * retry),
    ]
    assert results.original_retry_counts(grid) == dict(
        retry_visits=2, visits_with_repeated_retry_grid=1
    )
    with pytest.raises(ValueError, match="does not identify"):
        results.original_retry_counts([dict(calls=2, inverse_ffts=2 * primary + 1)])


def test_nested_ledger_separates_original_trigger_from_shared_grids(tmp_path):
    rows = [
        dict(
            ordinal=0,
            attempts=[[0, 12, False], [1, 12, True], [0, 22, True]],
            reuses=2,
            partial_bytes=400,
            merge_cpu_ns=350,
        ),
        dict(ordinal=1, attempts=[], reuses=0, partial_bytes=0, merge_cpu_ns=0),
    ]
    path = tmp_path / "cpu-2.log"
    grid = [
        dict(cpu=2, ordinal=i, status=s, visit=i)
        for i, s in enumerate(("processed", "invalid_capture"))
    ]
    path.write_text("".join(trial.NESTED_TRACE + json.dumps(r) + "\n" for r in rows))
    report = results.nested_retry_counts(tmp_path, grid)
    assert report["retries"] == report["rescues"] == 1
    assert report["additional_grids"] == 2
    assert report["per_receiver"] == {"0": {"retries": 1, "rescues": 1}}
    assert report["visits_with_repeated_addition"] == 1
    rows[0]["attempts"][2][0] = 1
    path.write_text("".join(trial.NESTED_TRACE + json.dumps(r) + "\n" for r in rows))
    with pytest.raises(ValueError, match="physical trigger changed"):
        results.nested_retry_counts(tmp_path, grid)


def test_full_factor_audit_distinguishes_alias_matches_and_changed_gates():
    def candidate(rank, epoch, cfo, gate=True):
        return dict(
            candidate_rank=rank,
            integer_epoch_sample=epoch,
            fractional_epoch_offset_samples=0,
            fractional_tracking_cfo_hz=cfo,
            fractional_margin=0.03 if gate else 0.02,
            passed_fractional_margin_gate=gate,
        )

    old = {
        "source": {
            "probes": [
                dict(visit_index=1, receiver_id=0, candidates=[candidate(0, 10, 100)]),
                dict(visit_index=1, receiver_id=1, candidates=[candidate(0, 70, 200)]),
            ]
        }
    }
    fresh = {
        "source": {
            "probes": [
                dict(
                    visit_index=1,
                    receiver_id=0,
                    candidates=[
                        candidate(2, 10, 100 + ALIAS_HZ),
                        candidate(1, 690, 500),
                    ],
                ),
                dict(visit_index=1, receiver_id=1, candidates=[candidate(0, 70, 200, False)]),
            ]
        }
    }
    report = results.factor_changes(fresh, old)
    assert report["old_candidates"] == 2 and report["new_candidates"] == 3
    assert report["old_passes"] == report["new_passes"] == 2
    assert report["old_only_passes"] == report["new_only_passes"] == report["matched_passes"] == 1
    assert report["lost_positive_probes"] == 1
    assert report["gained_positive_probes"] == 0
