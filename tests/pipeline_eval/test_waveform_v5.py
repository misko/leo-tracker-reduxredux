import pytest

from tools.pipeline_eval.qualification import waveform_v5 as trial
from tools.pipeline_eval.qualification import waveform_v5_results as results


def make_request(ident, lat):
    return {
        "id": ident,
        "session": "opaque",
        "native": "native.json",
        "native_sha256": "a" * 64,
        "track_config": "track-config.json",
        "config_sha256": "b" * 64,
        "archive": "tle",
        "catalog_sha256": "c" * 64,
        "screen_center": [lat, -67.5],
        "tile": [lat, -67.5],
    }


def test_three_holdout_offers_keep_original_screen_and_earliest_clock_edge():
    requests = [make_request(ident, lat) for ident, lat in (("b", 10), ("a", 10.1), ("c", 10.2))]
    document = dict(source={"session_id": "opaque"}, clock_anchor={"before": {"realtime_ns": 99}})
    rows = trial.request_pair(requests, document)
    assert [row["id"] for row in rows] == ["a", "b", "c"]
    assert [row["tile"][0] for row in rows] == [10.1, 10, 10.2]
    assert all(r["cutoff_utc_ns"] == 99 for r in rows)
    requests[2]["native_sha256"] = "d" * 64
    with pytest.raises(ValueError, match="native clock and session"):
        trial.request_pair(requests, document)


@pytest.mark.parametrize(("reason", "status"), [("timeout", "timed_out"), ("oom-kill", "failed")])
def test_incomplete_v5_service_does_not_publish_partial_position(tmp_path, reason, status):
    (tmp_path / "result.json").write_text('{"arms":{"c0":{"latlon":[0,0]}}}')
    result = trial.endpoint(tmp_path, 1, {"Result": reason}, "")
    assert result["status"] == status
    assert reason in result["reason"]
    assert result["arms"]["c0"]["latlon"] is None
    assert result["arms"]["fitted_c"]["latlon"] is None


def test_original_same_factor_binding_checks_catalogue_and_tile():
    request = make_request("case", 10)
    query = {"bindings": {"native_sha256": request["native_sha256"]}}
    base = {
        "id": "case",
        "input_sha256": trial.blind.digest_json(request),
        "native_sha256": request["native_sha256"],
        "catalogue_sha256": request["catalog_sha256"],
    }
    original = dict(
        base,
        method=trial.METHOD,
        service={"exit_code": 0},
        tile={"center": request["tile"], "width_km": 25},
        screen_center=request["screen_center"],
        config_sha256=request["config_sha256"],
    )
    compact = dict(base, method="compact")
    requests, queries, methods = {"case": request}, {"case": query}, (trial.METHOD, "compact")
    assert results.matched_rows([original, compact], requests, queries, methods, False)
    compact["catalogue_sha256"] = "f" * 64
    with pytest.raises(ValueError, match="same input"):
        results.matched_rows([original, compact], requests, queries, methods, False)
    original["tile"] = {"center": [11, -67.5], "width_km": 25}
    with pytest.raises(ValueError, match="offered tile"):
        results.matched_rows([original, compact], requests, queries, methods, False)
