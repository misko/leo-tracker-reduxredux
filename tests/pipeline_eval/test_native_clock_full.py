import pytest

from tools.pipeline_eval.qualification import native_clock_full as trial
from tools.pipeline_eval.qualification import native_clock_full_results as results


def test_clock_uses_exact_native_requests_and_sealed_inference_only(monkeypatch, tmp_path):
    original = trial.phase._read(trial.panel.REPORT / "plan.json")
    monkeypatch.setattr(trial.panel.base, "sources", lambda _bundle: original["source"])
    plan, jobs = trial.prepare(tmp_path)
    assert plan["cases"] == original["cases"]
    assert len(jobs) == 144
    query, files = jobs[0]
    argv = trial.command(trial.CPUS[0], files, tmp_path)
    assert str(trial.WORKER) in argv
    assert str(trial.base.WORKER) not in argv
    assert set(files) == {"native", "catalogue", "track_config"}
    assert query["packet"]["mode"] == "native"
    assert not any("/localization_v3/" in x or "/v5_" in x for x in argv)
    assert "--clock-off" not in argv


def test_joint_control_refuses_different_native_tile_or_graph():
    stock = dict.fromkeys((*results.PAIR_FIELDS, "recording", "cohort"), "same")
    stock["observation_sha256"] = "graph"
    candidate = dict(stock, result=dict(status="ok", metrics=dict(fixed_assignment_clock=True)))
    results.verified_pairs({"test": candidate}, {"test": stock})
    with pytest.raises(ValueError, match="different Graphs"):
        results.verified_pairs(
            {"test": dict(candidate, observation_sha256="other")}, {"test": stock}
        )
    with pytest.raises(ValueError, match="different requests"):
        results.verified_pairs({"test": dict(candidate, tile="other")}, {"test": stock})
    censored = dict(candidate, result=dict(status="timed_out", metrics={}))
    censored.pop("observation_sha256")
    results.verified_pairs({"test": censored}, {"test": stock})


def test_accuracy_counts_preserve_all_scheduled_and_only_compare_published_pairs():
    one = dict(
        cohort="roof",
        dataset="DS26",
        arm="c0",
        exact_graph=True,
        status="ok",
        joint_status="ok",
        error_km=1.06,
        joint_error_km=1.0,
        forced_error_km=1.06,
        joint_forced_error_km=1.0,
        conditional_rms_hz=90,
        joint_conditional_rms_hz=100,
        held_score=0.5,
        joint_held_score=0.4,
        held_orbits=4,
        joint_held_orbits=4,
        clock_held_rf_rms_hz=200,
    )
    two = dict(one, status="withheld", error_km=None)
    table = results.comparisons([one, two])[0]
    assert table["scheduled"] == 2
    assert table["paired_accuracy"]["pairs"] == 1
    assert table["paired_accuracy"]["at_most_5pct_worse"] == 0
    assert table["paired_accuracy"]["at_most_10pct_worse"] == 1
    assert table["clock_minus_joint"]["conditional_rms_hz"]["n"] == 2
