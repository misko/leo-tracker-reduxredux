import json
from hashlib import sha256
from types import SimpleNamespace

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval.position_figure import Mark
from tools.pipeline_eval.qualification import original_support_benchmark as benchmark
from tools.pipeline_eval.qualification.original_support_overlap import compare_trace, equal_payload


def test_queue_overlap_checks_physical_clock_and_emitted_visit_membership():
    ledger = [
        dict(visit=0, arrival_ns=100, sample_start=71, status="processed"),
        dict(visit=1, arrival_ns=200, sample_start=81, status="invalid_capture"),
        dict(visit=2, arrival_ns=300, sample_start=91, status="processed"),
        dict(visit=3, arrival_ns=400, sample_start=101, status="processed"),
    ]
    forecast = [(0, 100, 130), (2, 300, 370)]
    trace = [
        dict(
            ledger[0],
            outcome="emitted",
            started_ns=100,
            emitted_ns=150,
            native_cpu_ns=45,
            native_wall_ns=50,
        ),
        dict(ledger[1], outcome="invalid_capture"),
        dict(ledger[2], outcome="queue_drop"),
        dict(
            ledger[3],
            outcome="emitted",
            started_ns=410,
            emitted_ns=490,
            native_cpu_ns=39,
            native_wall_ns=80,
        ),
    ]
    result = compare_trace(ledger, forecast, trace)
    assert result["valid_arrivals"] == 3
    assert result["modeled_emitted"] == result["live_emitted"] == 2
    assert result["overlap"] == result["only_live"] == result["only_modeled"] == 1
    assert result["jaccard"] == 1 / 3
    assert result["live_age_median_ms"] == pytest.approx(0.00007)
    assert compare_trace(ledger, forecast)["live_emitted"] is None
    with pytest.raises(ValueError, match="physical delivery/sample clocks"):
        compare_trace(ledger, forecast, [dict(trace[0], sample_start=72), *trace[1:]])
    with pytest.raises(ValueError, match="terminal state"):
        compare_trace(
            ledger, forecast, [trace[0], dict(trace[1], outcome="queue_drop"), *trace[2:]]
        )


def test_periodic_parity_compares_factor_content_and_physical_support():
    base = dict(
        source=dict(probes=[dict(candidates=[dict(hz=4)])], analysis_manifest_sha256="stored"),
        delivery_clocks=[dict(monotonic_ns=8)],
        clock_anchor="recorded",
        last_sample_counter=12,
        provenance=dict(excluded_windows=[dict(visit=3)], run_id="stored"),
    )
    live = dict(
        base,
        source=dict(base["source"], analysis_manifest_sha256="live"),
        provenance=dict(base["provenance"], run_id="live"),
    )
    equal_payload(base, live)
    with pytest.raises(ValueError, match="different probes or clocks"):
        equal_payload(base, dict(live, source=dict(live["source"], probes=[])))
    with pytest.raises(ValueError, match="different probes or clocks"):
        equal_payload(base, dict(live, delivery_clocks=[dict(monotonic_ns=9)]))


def test_original_support_named_dispatch_and_source_scope(monkeypatch, tmp_path):
    folder = tmp_path / "benchmark"
    folder.mkdir()
    (folder / "figures.json").write_text(json.dumps({"charts": [{"id": "local"}]}))
    index, _, ledger, _, _ = benchmark.catalog(tmp_path)
    assert index == []
    assert "benchmark" not in ledger
    assert ledger["queue-selection"]["state"] == "awaiting_seal"
    calls = []
    monkeypatch.setattr(benchmark, "run", calls.append)
    assert cli.main(["benchmark", "--receiver", "original-support", "--out", str(folder)]) == 0
    assert calls == [folder]


def test_lane_screen_is_sealed_detector_cost_only(tmp_path):
    study = tmp_path / "lane-screen"
    study.mkdir()
    table = study / "stage.csv"
    table.write_text("mode,cpu_ms\nheld,20.41\n")
    (study / "stage-figure.json").write_text(
        json.dumps(
            {
                "id": "lane-screen",
                "seal": "result-lock.json",
                "boundary": "raw to native",
                "csv": table.name,
            }
        )
    )
    (study / "result-lock.json").write_text(
        json.dumps(
            {
                "files": {table.name: sha256(table.read_bytes()).hexdigest()},
            }
        )
    )
    pages, stages, ledger, assets, _ = benchmark.catalog(tmp_path)
    assert pages == [] and [stage["id"] for stage in stages] == ["lane-screen"]
    assert ledger["lane-screen"] == {
        "state": "stage_only",
        "position_charts": 0,
        "stage_available": True,
    }
    [clock] = benchmark.cost_summary(tmp_path, assets)
    assert clock["p50"] == 20.41 and clock["evidence"] == "measured detector replay"
    table.write_text("mode,cpu_ms\nheld,20.0\n")
    with pytest.raises(ValueError, match="file differs from declared SHA-256"):
        benchmark.catalog(tmp_path)


def test_rf_and_coverage_keep_distinct_transfer_offers_with_same_recording():
    def point(hz):
        return dict(method="method", result=dict(arms={"c0": {"rf_rms_hz": hz}}, metrics={}))

    study = SimpleNamespace(
        id="transfer",
        scope="transfer",
        labels={},
        references={case: {"condition": "omitted", "recording": "same"} for case in ("a", "b")},
        predictions={"candidate": {"a": point(21), "b": point(25)}},
        page=lambda _arm: SimpleNamespace(
            rows=[
                Mark("omitted", "same", "candidate", "withheld", None),
                Mark("omitted", "same", "candidate", "withheld", None),
                Mark("omitted", "same", "candidate_forced", "diagnostic", 2.0),
            ]
        ),
    )
    summary, rf, _ = benchmark.score_charts([study], {"transfer": "scope"})
    zero, fit = summary
    assert [r["id"] for r in rf if r["arm"] == "c0"] == ["a", "b"]
    assert (zero["scheduled"], zero["withheld"], zero["rf_n"], zero["rf_p50_hz"]) == (2, 2, 2, 23)
    assert zero["median_km"] is None and zero["within_10pct"] is None
    assert fit["rf_n"] == 0
