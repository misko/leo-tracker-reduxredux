from tools.pipeline_eval.qualification import exact_wide_iq as trial
from tools.pipeline_eval.qualification import exact_wide_iq_results as results


def test_holdout_rank_uses_only_the_first_manifest_and_prior_whole_iq_roster():
    inputs = {
        ident: {"recording": {"segments": [{"sha256": first}, {"sha256": later}]}}
        for ident, first, later in (
            ("DS26-0001", "c", "0"),
            ("DS26-0002", "b", "z"),
            ("DS26-0003", "a", "q"),
        )
    }
    assert trial.ranked(inputs, tuple(inputs), {"DS26-0003"}) == [
        ("b", "DS26-0002"),
        ("c", "DS26-0001"),
    ]
    assert trial.scheduled({"cases": {"DS26-0001": {}, "other": {}}, "case": "DS29-0082"}) == [
        "DS26-0001",
        "DS29-0082",
    ]


def test_export_comparison_does_not_hide_signed_zero_or_drop_missing_visits():
    a = [{"visit": 0, "probes": [{"candidates": [{"tracking": -0.0}]}]}]
    b = [{"visit": 0, "probes": [{"candidates": [{"tracking": 0.0}]}]}]
    assert results.exact_visits(a, a)["mismatches"] == 0
    assert results.exact_visits(a, b)["first_mismatched_visits"] == [0]
    assert results.exact_visits(a, [])["mismatches"] == 1


def test_library_provenance_normalizes_without_copying_away_scientific_fields():
    value = dict(
        source={
            "analysis_manifest_sha256": "old-analysis",
            "input_manifest_sha256": "archive",
            "probes": [{"candidates": ["positive"]}],
        },
        provenance={"run_id": "one", "detector_sha256": "old-binary", "excluded_windows": [1]},
        delivery_clocks=[29],
    )
    output = results.normalized_document(value)
    assert output["delivery_clocks"] == [29]
    assert output["source"]["probes"] == value["source"]["probes"]
    assert output["source"]["input_manifest_sha256"] == "archive"
    assert output["provenance"] == {"excluded_windows": [1]}
    assert value["provenance"]["detector_sha256"] == "old-binary"


def test_twenty_ms_stock_and_candidate_metrics_use_measured_wall_and_cpu_separately():
    resources = {"DS26-0001": {"control": {"service": {}, "dual_calls": 2}}}
    values = [
        dict(id="DS26-0001", role="control", wall_s=wall, cpu_s=cpu)
        for wall, cpu in ((0.020, 0.019), (0.021, 0.017))
    ]
    (score,) = results.timing_rows(resources, values)
    assert score["wall_within_20ms"] == 1
    assert score["cpu_within_20ms"] == 2
    assert score["call_wall_p50_ms"] == 20.5
    assert score["call_cpu_p50_ms"] == 18.0


def test_published_exact_wide_iq_scores_and_timing_reproduce_offline(tmp_path):
    source = trial.REPORT
    results.score(source, tmp_path)
    audit = results.whole_iq.read(source / results.NATIVE_PARITY)
    assert set(audit) == {"DS26-0241", "DS29-0357"}
    assert sum(row["compared_visits"] for row in audit.values()) == 13_547
    for row in audit.values():
        assert row["mismatches"] == 0 and row["positions_exact"]
    for name in ("scores.csv", results.COMPARE):
        assert (tmp_path / name).read_bytes() == (source / name).read_bytes()
