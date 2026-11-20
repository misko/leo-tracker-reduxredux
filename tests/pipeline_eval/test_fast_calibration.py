import pytest

from tools.pipeline_eval.qualification import fast_calibration_model as model
from tools.pipeline_eval.qualification import fast_calibration_trial as trial


def candidate(cfo, *, rank=1, margin=0.08, gate=True, epoch=100):
    return {
        model.CFO: cfo,
        model.GATE: gate,
        "candidate_rank": rank,
        "fractional_margin": margin,
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.1,
    }


def native(items):
    source = dict(
        session_id="session",
        input_manifest_sha256="capture",
        raw_recording_authority_digest="raw",
        sample_rate_hz=10_000_000,
        probe_ms=20,
        radio_id="radio",
        stream_generation="clock",
        capture_mode="adaptive",
        probes=[
            dict(
                visit_index=i // 2,
                receiver_id=i % 2,
                edge="upper",
                actual_rf_hz=11_000_000_000,
                candidates=cand,
            )
            for i, cand in enumerate(items)
        ],
    )
    return dict(
        source=source,
        provenance=dict(excluded_windows=[]),
        schema_version=1,
        clock_anchor={},
        delivery_clocks=[],
        last_sample_counter=11,
    )


def test_literal_matching_distinguishes_alias_rejected_and_nonwinning_support():
    original = native([[candidate(1000)] for _ in range(4)])
    fast = native(
        [
            [candidate(990, epoch=100 + 13333)],
            [candidate(1000 + model.ALIAS_HZ)],
            [candidate(999, gate=False, margin=0.02)],
            [candidate(1000, rank=2, margin=0.04), candidate(99_000, rank=1)],
        ]
    )
    rows, census = model.pairs("r", fast, original)
    assert len(rows) == 1 and rows[0]["difference_hz"] == 10
    assert census["literal_winners"] == census["aliased_winners"] == census["literal_rejected"] == 1
    assert census["literal_positive_alternate"] == census["different_winners"] == 1
    assert census["original_only"] == 1


def test_frozen_correction_preserves_rejected_candidates_and_physical_authority():
    start = native([[candidate(-500), candidate(999, gate=False, margin=0.02)], []])
    doc, count = model.apply(start, {"name": "offset", "offset_hz": -0.75})
    assert count == 1
    assert doc["provenance"] == start["provenance"]
    assert doc["clock_anchor"] == start["clock_anchor"]
    a, b = doc["source"]["probes"][0]["candidates"]
    c, d = start["source"]["probes"][0]["candidates"]
    assert a == dict(c, **{model.CFO: -500.75})
    assert b == d
    reverse, _ = model.apply(start, {"name": "offset", "offset_hz": -0.75}, -1)
    assert reverse["source"]["probes"][0]["candidates"][0][model.CFO] == -499.25
    with pytest.raises(ValueError, match="sign"):
        model.apply(start, {"name": "offset", "offset_hz": 1}, 0)


def test_splits_uses_physical_edge_and_model_complexity_requires_transfer_gain():
    metadata = {
        f"{edge}-{i}": dict(edge=edge, manifest=str(i)) for edge in trial.EDGES for i in range(8)
    }
    frozen = trial.split(metadata)
    for e in trial.EDGES:
        assert len(set(frozen["held"][e]) | set(frozen["development"][e])) == 7
        assert not set(frozen["held"][e]) & set(frozen["development"][e])
    groups = {
        case: [
            dict(id=case, edge="lower", rf=1, fast_cfo_hz=float(x), difference_hz=1.25)
            for x in range(10)
        ]
        for case in ("a", "b", "c")
    }
    name, models, _, loss = model.choose(groups)
    assert name == "offset"
    assert models["offset"]["offset_hz"] == 1.25
    assert loss["offset"] == 0
