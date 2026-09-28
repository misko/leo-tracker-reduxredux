import math

import pytest

from tools.rx_ds8_alignment import analyze


def _window(session, index, role, seconds, aligned, *, invisible_second=False, empty_rx1=False):
    observed = {
        "rx0": [{"candidate_id": f"{session}-{index}-0", "canonical_rx0_hz": 995.0}]
        if aligned
        else [],
        "rx1": []
        if empty_rx1
        else [{"candidate_id": f"{session}-{index}-1", "canonical_rx0_hz": 5.0}],
    }
    return {
        "source_window_id": f"{session}-{index}",
        "role": role,
        "prediction_utc_ns": int(seconds * 1e9),
        "sample_rate_hz": 5_000_000,
        "observed": observed,
        "predictions": [
            {
                "track_id": "t0",
                "catalog_number": 10,
                "mu_canonical_rx0_hz": 5.0,
                "visible": True,
            },
            {
                "track_id": "t1",
                "catalog_number": 11,
                "mu_canonical_rx0_hz": 5.0,
                "visible": not invisible_second,
            },
        ],
    }


def _lane(session, reception_alignments=(True,), *, invisible_second=False, empty_rx1=False):
    windows = [
        _window(
            session,
            index,
            "reception",
            100 + index * 10,
            aligned,
            invisible_second=invisible_second,
            empty_rx1=empty_rx1,
        )
        for index, aligned in enumerate(reception_alignments)
    ]
    windows.append(
        _window(
            session,
            len(windows),
            "held_frequency",
            200,
            reception_alignments[-1],
            invisible_second=invisible_second,
            empty_rx1=empty_rx1,
        )
    )
    return {
        "recording_split": "evaluation",
        "lane": {"session_id": session, "channel": 0, "edge": "lower"},
        "alias_period_hz": 1_000.0,
        "components": [
            {"kind": "track_candidate", "track_id": "t0", "catalog_number": 10, "log_prior": 0.0},
            {
                "kind": "track_candidate",
                "track_id": "t1",
                "catalog_number": 11,
                "log_prior": 0.0,
            },
            {"kind": "other", "log_prior": None},
        ],
        "windows": windows,
    }


def _document(lanes=None):
    if lanes is None:
        lanes = [_lane(f"s{index}") for index in range(4)]
    return {"schema": "rx-geometry-dataset/v1", "lanes": lanes}


def test_wrapping_empty_and_invisible_nominees_contribute_zero_alignment():
    lane = _lane("s0", invisible_second=True, empty_rx1=True)
    document = _document([lane, _lane("s1"), _lane("s2"), _lane("s3")])
    result = analyze(document)
    window = result["lanes"][0]["windows"][0]
    assert window["nominees"][0]["receivers"]["rx0"]["nearest"][
        "signed_residual_hz"
    ] == pytest.approx(-10.0)
    assert window["metrics"]["rx0_within_500hz"] == pytest.approx(0.5)
    assert window["metrics"]["rx1_within_500hz"] == 0.0
    assert window["metrics"]["paired_500hz_rx0_only"] == pytest.approx(0.5)
    assert window["metrics"]["paired_500hz_neither"] == pytest.approx(0.5)


def test_pair_states_use_normalized_nominee_weights():
    lane = _lane("s0", invisible_second=True, empty_rx1=True)
    lane["components"][0]["log_prior"] = 0.0
    lane["components"][1]["log_prior"] = math.log(3.0)
    result = analyze(_document([lane, _lane("s1"), _lane("s2"), _lane("s3")]))
    metrics = result["lanes"][0]["windows"][0]["metrics"]
    assert metrics["paired_500hz_rx0_only"] == pytest.approx(0.25)
    assert metrics["paired_500hz_neither"] == pytest.approx(0.75)
    assert metrics["prior_weighted_visible"] == pytest.approx(0.25)
    assert metrics["rx0_observed"] == 1.0
    assert metrics["rx1_observed"] == 0.0
    assert sum(
        metrics[f"paired_500hz_{name}"]
        for name in ("both", "rx0_only", "rx1_only", "neither")
    ) == pytest.approx(1.0)


def test_equal_record_aggregation_is_not_window_pooled_and_bins_are_sparse():
    lanes = [_lane("s0", (True, True, True))]
    lanes.extend(_lane(f"s{index}", (False,)) for index in range(1, 4))
    result = analyze(_document(lanes))
    reception = result["aggregate_equal_record"]["roles"]["reception"]
    assert reception["windows"] == 6
    assert reception["metrics"]["rx0_within_500hz"] == pytest.approx(0.25)
    bins = result["aggregate_equal_record"]["elapsed_bins"]
    assert "reception:0-30" in bins
    assert "reception:30-60" not in bins
    assert bins["reception:0-30"]["records"] == 4


def test_rejects_non_evaluation_input():
    document = _document()
    document["lanes"][0]["recording_split"] = "calibration"
    with pytest.raises(ValueError, match="evaluation lanes only"):
        analyze(document)
