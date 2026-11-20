import pytest

from tools.pipeline_eval.qualification import single_pass_position as trial
from tools.pipeline_eval.qualification import single_pass_position_results as results


def probe(visit, receiver, gates):
    return dict(
        visit_index=visit,
        receiver_id=receiver,
        actual_rf_hz=10_700_000_000.0,
        candidates=[
            dict(candidate_rank=i, passed_fractional_margin_gate=passed)
            for i, passed in enumerate(gates, 1)
        ],
    )


def grid(visit, primary, wide, *, status="processed"):
    calls = primary + wide
    return dict(
        visit=visit,
        status=status,
        calls=calls,
        inverse_ffts=primary * 104_286 + wide * 191_037,
        input_ffts=calls * 427,
        spans=calls * 21 * 13_333,
    )


def test_grid_ledger_distinguishes_tie_repeats_from_wide_retry():
    probes = {
        0: (probe(0, 0, [True]), probe(0, 1, [True])),
        1: (probe(1, 0, [True]), probe(1, 1, [False])),
        2: (probe(2, 0, [True]), probe(2, 1, [True])),
    }
    visits = [grid(0, 3, 0), grid(1, 2, 1), grid(2, 2, 2), grid(3, 0, 0, status="invalid_capture")]
    assert trial.census(visits, probes, {3}) == {0: (3, 0), 1: (2, 1), 2: (2, 2), 3: (0, 0)}
    with pytest.raises(ValueError, match="duplicate"):
        trial.census(visits + visits[:1], probes, {3})
    with pytest.raises(ValueError, match="physical gate"):
        trial.census([visits[0], grid(1, 2, 0), *visits[2:]], probes, {3})


def test_merge_preserves_the_rejections_and_complete_physical_capture():
    original = [
        probe(0, 0, [True, False]),
        probe(0, 1, [True, True]),
        probe(1, 0, []),
        probe(1, 1, [False]),
    ]
    document = dict(
        source=dict(probes=original, analysis_manifest_sha256="source", session_id="recording"),
        provenance=dict(detector_sha256="original", excluded_windows=[{"visit": 2}]),
        clock_anchor={"counter": 123},
        delivery_clocks=[{"clock": 567}],
        last_sample_counter=100,
    )
    primary = [original[0], probe(0, 1, [False, False, False])]
    rows = {0: dict(probes=primary, attempts=[[0, 12, True], [1, 12, False]])}
    native, changes = results.merge(document, rows, [0], "binding")
    assert native["source"]["probes"] == primary + original[2:]
    assert native["source"]["session_id"] == "recording"
    assert native["source"]["analysis_manifest_sha256"] != "source"
    assert native["provenance"]["excluded_windows"] == [{"visit": 2}]
    assert native["provenance"]["detector_sha256"] != "original"
    assert all(
        native[k] == document[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")
    )
    assert [(r["conditional_gate"], r["primary_gate"]) for r in changes] == [(1, 1), (2, 0)]
    assert document["source"]["probes"] == original

    with pytest.raises(ValueError, match="replacement roster"):
        results.merge(document, rows, [0, 1], "binding")
    rows[0]["probes"] = [primary[0], {**primary[1], "actual_rf_hz": 0}]
    with pytest.raises(ValueError, match="physical authority"):
        results.merge(document, rows, [0], "binding")
