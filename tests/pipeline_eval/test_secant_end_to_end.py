import json

import pytest

from tools.pipeline_eval.__main__ import read_predictions
from tools.pipeline_eval.qualification import secant_end_to_end, secant_end_to_end_worker


def test_capture_duration_uses_device_counter_with_retune_gaps():
    source = dict(
        clock_anchor={"sample_counter": 7_002_033_432_340},
        last_sample_counter=7_005_033_432_341,
        source={"sample_rate_hz": 10_000_000},
    )
    assert secant_end_to_end.capture_duration(source) == 300.0000001


def test_instrumentation_keeps_call_result_and_counts_multiple_calls():
    stages = {}
    capture = []

    def operation(value):
        capture.append(value)
        return value + 5

    measured = secant_end_to_end_worker.measured(operation, "fixture", stages)
    assert measured(2) == 7
    assert measured(5) == 10
    assert capture == [2, 5]
    assert stages["fixture"]["calls"] == 2
    assert all(stages["fixture"][key] >= 0 for key in ("wall_s", "cpu_s", "self_peak_rss_kib"))


def fake_replays(directory, wrong_sha=False):
    for case in secant_end_to_end.CASES:
        folder = directory / case
        folder.mkdir()
        stage = {"raw_replay": {"native_sha256": case + ":fresh"}}
        (folder / "stage-receipt.json").write_text(json.dumps(stage))
        for mode in secant_end_to_end.METHODS:
            worker = folder / mode
            worker.mkdir()
            job = dict(output_root=str(worker), search_center=[30, 30])
            (worker / "request.json").write_text(json.dumps({"job": job}))
            row = dict(
                id=case,
                native_sha256="wrong" if wrong_sha and mode == "reference" else case + ":fresh",
                catalog_sha256="frozen-causal-elements",
                tile=dict(center=[30, 30], width_km=25),
                raw_replayed_here=mode == "secant",
                result=dict(
                    status="ok",
                    boundary="test",
                    metrics={},
                    arms={"c0": {"latlon": [30, 30]}, "fitted_c": {"latlon": [31, 31]}},
                ),
            )
            (folder / f"{mode}-position.json").write_text(json.dumps(row))


def test_publication_requires_identical_factors_and_raw_scope(tmp_path):
    fake_replays(tmp_path)
    output = tmp_path / "out"
    secant_end_to_end.publish(tmp_path, output)
    chain = read_predictions(output / "positions.jsonl.gz")
    stock = read_predictions(output / "stock-positions.jsonl.gz")
    for case in secant_end_to_end.CASES:
        assert chain[case]["native_sha256"] == stock[case]["native_sha256"]
        assert chain[case]["raw_replayed_here"] and not stock[case]["raw_replayed_here"]


def test_publication_rejects_a_different_stock_factor_file(tmp_path):
    fake_replays(tmp_path, wrong_sha=True)
    with pytest.raises(ValueError, match="same freshly measured IQ"):
        secant_end_to_end.publish(tmp_path, tmp_path / "out")


def test_publication_rejects_a_different_position_prior(tmp_path):
    fake_replays(tmp_path)
    path = tmp_path / secant_end_to_end.CASES[0] / "reference" / "request.json"
    request = json.loads(path.read_text())
    request["job"]["search_center"] = [30.5, 31]
    path.write_text(json.dumps(request))
    with pytest.raises(ValueError, match="different scientific requests"):
        secant_end_to_end.publish(tmp_path, tmp_path / "out")
