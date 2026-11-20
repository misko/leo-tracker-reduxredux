"""Check retrospective retry composition and its sealed position controls."""

from unittest.mock import patch

import pytest

from tools.pipeline_eval.qualification import retry_policy_pair as pair
from tools.pipeline_eval.qualification import retry_policy_pair_results as results


def test_retrospective_materializer_preserves_full_support_and_exact_retry_rows():
    initial = {1: ({"tag": "failed"}, {"tag": "good"}), 5: ({"tag": "plain"}, {"tag": "plain"})}
    full = initial | {1: ({"tag": "retry"}, initial[1][1])}
    original = {
        "schema_version": 1,
        "clock_anchor": {},
        "delivery_clocks": [],
        "last_sample_counter": 20,
        "source": {
            "probes": [p for probes in full.values() for p in probes],
            "analysis_manifest_sha256": "original",
            "session_id": "s",
        },
        "provenance": {"window_count": 6, "invalid_capture": 4, "excluded_windows": [0, 2, 3, 4]},
    }
    timer = pair.materialize("case", original, initial, full, {1}, pair.frozen.TWO, "bound")
    hash_ = pair.materialize("case", original, initial, full, set(), pair.frozen.CONTROL, "bound")
    assert timer["source"]["probes"] == original["source"]["probes"]
    assert hash_["source"]["probes"] == [p for probes in initial.values() for p in probes]
    assert (
        timer["source"]["analysis_manifest_sha256"] != hash_["source"]["analysis_manifest_sha256"]
    )
    assert timer["provenance"]["excluded_windows"] == hash_["provenance"]["excluded_windows"]


def test_census_must_match_known_selection_before_positions():
    data = [
        dict(policy=pair.frozen.TWO, attempts=1063, rescues=392),
        dict(policy=pair.frozen.CONTROL, attempts=1062, rescues=303),
    ]
    with (
        patch.object(pair.frozen, "counters", return_value=({}, {}, [], {}, data)),
        pytest.raises(ValueError, match="counts disagree"),
    ):
        pair.measured_support("DS26-0237", None, None)


def test_one_v2_figure_uses_three_original_request_matched_series():
    spec = results.descriptor()
    assert spec["version"] == 2
    (chart,) = spec["charts"]
    assert {series["value"] for series in chart["series"]} == set(pair.METHODS.values())
    assert all(series["match"] == results.MINIMAL for series in chart["series"])
