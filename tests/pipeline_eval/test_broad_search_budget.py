import pytest

from tools.pipeline_eval.qualification import broad_search_budget as experiment


def test_roster_uses_rank_and_hash_without_timing_overlap():
    ranks = {
        "DS26-0201": 0,
        "DS26-0062": 0,
        "DS26-0006": 0,
        "DS26-0036": 1,
        "DS29-0082": 0,
        "DS26-0118": 2,
    }
    disagree, controls = experiment.select_roster(ranks, experiment.TIMING_IDS)
    assert disagree == ["DS26-0036", "DS26-0118"]
    assert controls == ["DS26-0201", "DS26-0062", "DS26-0006"]


def test_rank_zero_without_compact_equality_has_no_candidate_fix_or_timing(tmp_path):
    ident = "DS29-0127"
    fixed = dict(winning_ranks={ident: 0}, fresh_cases=[], timing_cases=[])
    item = dict(native={"sha256": "native"}, catalog={"sha256": "catalog"})
    record = experiment._candidate_record(ident, item, {"id": ident}, fixed, tmp_path, tmp_path)
    assert record["source"] == "unmeasured_agreement"
    assert record["result"]["status"] == "missing"
    assert record["result"]["arms"] == {arm: {"latlon": None} for arm in experiment.ARMS}
    assert "worker_wall_s" not in record
    fixed["winning_ranks"][ident] = 1
    with pytest.raises(ValueError, match="missing its fresh replay"):
        experiment._candidate_record(ident, item, {"id": ident}, fixed, tmp_path, tmp_path)


def test_replayed_failure_keeps_its_boundary_and_time(monkeypatch, tmp_path):
    ident = "DS26-0044"
    fixed = dict(winning_ranks={ident: 2}, fresh_cases=[ident], timing_cases=[], source="seal")
    item = dict(id=ident, native={"sha256": "h1"}, catalog={"sha256": "h2"})
    case = {"id": ident}
    run = dict(
        id=ident,
        method=experiment.METHOD,
        input_sha256=experiment.projector_roof.input_hash(case),
        source_sha256="seal",
        native_sha256="h1",
        catalog_sha256="h2",
        source="broad_fresh",
        cap_s=600,
        worker_wall_s=600.1,
        result=dict(status="timed_out", reason="deadline", boundary="worker", metrics={}),
    )
    monkeypatch.setattr(experiment, "_read", lambda _: run)
    monkeypatch.setattr(experiment.search_budget, "digest", lambda _: "run hash")
    record = experiment._candidate_record(ident, item, case, fixed, tmp_path, tmp_path)
    assert record["method"] == experiment.BROAD
    assert record["result"] == run["result"]
    assert record["worker_wall_s"] == 600.1
    assert record["original_run_sha256"] == "run hash"


def test_scoring_requires_sealed_predictions_before_opening_references(monkeypatch, tmp_path):
    def unexpected_roster():
        pytest.fail("reference labels opened without a valid prediction seal")

    monkeypatch.setattr(experiment.projector_roof, "roster", unexpected_roster)
    with pytest.raises(FileNotFoundError, match="receipt.json"):
        experiment.score(tmp_path)
    (tmp_path / "receipt.json").write_text('{"files": {"plan.json": "untrusted"}}')
    with pytest.raises(ValueError, match="predictions differ from their seal"):
        experiment.score(tmp_path)


def test_scheduled_coverage_and_conditional_comparator_have_separate_denominators():
    common = dict(
        dataset="DS26",
        arm="c0",
        candidate_to_baseline_km=None,
        candidate_to_stock_km=None,
        archived_stock_worker_wall_s=100.0,
        fresh_worker_wall_s=None,
        timing_study_worker_wall_s=None,
        orbit_projector_error_km=1.5,
        orbit_projector_conditional_rms_hz=95.0,
        baseline_error_km=2.0,
        baseline_conditional_rms_hz=100.0,
    )
    rows = [
        dict(
            common,
            candidate_status="missing",
            source="unmeasured_agreement",
            original_winning_rank=0,
            v5_first_ranked_broad_error_km=None,
            v5_first_ranked_broad_conditional_rms_hz=None,
        ),
        dict(
            common,
            candidate_status="ok",
            source="broad_fresh",
            original_winning_rank=1,
            v5_first_ranked_broad_error_km=3.0,
            v5_first_ranked_broad_conditional_rms_hz=85.0,
            fresh_worker_wall_s=80.0,
        ),
    ]
    summaries = {r["cohort"]: r for r in experiment._summary(rows) if r["dataset"] == "all"}
    all_attempts = summaries["scheduled"]
    assert all_attempts["scheduled"] == 2
    assert all_attempts["candidate_published"] == all_attempts["fresh_worker_wall_s"]["n"] == 1
    baseline = all_attempts["methods"]["baseline"]
    assert baseline["error_km"]["n"] == 2
    assert baseline["within_km"] == {"1": 0, "2": 2, "5": 2, "10": 2}
    assert baseline["on_candidate_published_error_km"]["n"] == 1
    assert baseline["paired_errors"]["error_difference_km"]["p50"] == 1.0
    assert baseline["paired_errors"]["worsened_over_100m"] == 1
    assert baseline["paired_errors"]["at_most_10pct_worse"] == 0
    assert summaries["replayed"]["scheduled"] == 1
