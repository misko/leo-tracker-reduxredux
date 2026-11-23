from importlib import import_module
from pathlib import Path

import pytest


@pytest.mark.parametrize("fitted_delta,expected", [(0.25, True), (0.251, False), (None, False)])
def test_northern_screen_requires_both_calibrations_and_independent_omissions(
    monkeypatch, fitted_delta, expected
):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    gates = import_module("north_combined").gates
    rows = {
        "containing": {
            "decision": "complete",
            "process": {"elapsed_s": 6},
            "score": {
                "arms": {
                    "c0": {"delta_error_km": -0.01},
                    "fitted_c": {"delta_error_km": fitted_delta},
                }
            },
        },
        "stock": {"process": {"elapsed_s": 10}},
        "north-mirror-outside": {"decision": "complete"},
        "north-far": {"decision": "withheld"},
    }
    result = gates(rows)
    assert result["containing"] is expected
    assert result["elapsed_fraction"] == 0.6
    assert result["omissions"] == {"north-mirror-outside": False, "north-far": True}


def test_intersection_binds_both_packets_and_keeps_original_candidate_measurements(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    intersection = import_module("north_factor_swap").intersection

    def make(factors):
        return dict(
            source=dict(
                probes=[dict(visit_index=i, candidates=rows) for i, rows in enumerate(factors)],
                raw_recording_authority_digest="test",
            ),
            provenance=dict(detector_sha256="original"),
        )

    stock, candidate = make([[11], []]), make([[12], [13]])
    filtered = intersection(stock, candidate)
    assert [p["candidates"] for p in filtered["source"]["probes"]] == [[12], []]
    assert candidate["source"]["probes"][1]["candidates"] == [13]
    assert filtered["provenance"]["detector_sha256"] != candidate["provenance"]["detector_sha256"]
    assert filtered["provenance"] != intersection(make([[10], []]), candidate)["provenance"]
    stock["source"]["probes"][1]["visit_index"] = 7
    with pytest.raises(ValueError, match="identical signed"):
        intersection(stock, candidate)


def test_raw_history_is_causal_and_separate_for_each_radio(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    module = import_module("causal_short_receiver")
    from leo.contracts.digests import canonical_digest

    recipe, digest = module.identity("0" * 64)
    assert canonical_digest(recipe) == "sha256:" + digest
    history = module.carrier_continuation.Continuation()
    factor = dict(fractional_tracking_cfo_hz=13000, fractional_margin=0.3, candidate_rank=0)

    def row(i, lane):
        return dict(
            channel=1,
            actual_rf_hz=10e9,
            receiver_id=lane,
            valid_start_counter=i * 2_000_000,
            candidates=[factor],
        )

    assert [module.select(history, row(i, 0))["candidates"] for i in range(4)] == [
        [],
        [],
        [],
        [factor],
    ]
    assert module.select(history, row(3, 1))["candidates"] == []
