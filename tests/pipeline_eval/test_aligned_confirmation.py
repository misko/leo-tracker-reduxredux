import pytest

from tools.pipeline_eval.qualification import aligned_confirmation as trial
from tools.pipeline_eval.qualification import aligned_confirmation_results as results


def test_roster_is_hash_selected_without_retrospective_or_stress_cases():
    ids = trial.phase.frozen_inputs()
    cohorts = trial.roster(ids)
    assert cohorts["confirmation"][:8] == [
        "DS26-0012",
        "DS26-0223",
        "DS26-0076",
        "DS26-0030",
        "DS26-0175",
        "DS26-0114",
        "DS26-0058",
        "DS26-0052",
    ]
    assert len(cohorts["confirmation"]) == 15
    assert len(cohorts["stress"]) == 4
    assert not set(cohorts["confirmation"]) & (set(trial.old.PINS) | set(cohorts["stress"]))
    assert cohorts == trial.roster(reversed(ids))


def test_runtime_request_matches_after_only_relocating_output(tmp_path):
    native_input = dict(path=str(tmp_path / "native"), sha256="plain example")
    base = dict(job=dict(output_root="build", native_input=native_input, evaluation_reference=None))
    expected = tmp_path / "expected.json"
    actual = tmp_path / "actual.json"
    trial.save_json(expected, base)
    moved = dict(base, job=dict(base["job"], output_root="worker"))
    trial.save_json(actual, moved)
    assert trial._request_proof({"request_path": expected}, actual)["scientific_request_sha256"]
    moved["job"]["evaluation_reference"] = [0, 0]
    trial.save_json(actual, moved)
    with pytest.raises(ValueError, match="exact numerical request"):
        trial._request_proof({"request_path": expected}, actual)


def test_model_objective_and_frequency_rms_are_not_interchangeable():
    arms = {"c0": {"latlon": [20.0, -50.0], "rf_rms_hz": 75.0}}
    cavity = dict(arms=arms, metrics={})
    finish = dict(arms=arms, metrics={"c0_conditional_rms_hz": 70.0, "c0_frequency_score": -12.5})
    assert results._fields(cavity, "c0")["objective"] is None
    assert results._fields(cavity, "c0")["conditional_doppler_rms_hz"] == 75.0
    assert results._fields(finish, "c0")["objective"] == -12.5
    assert results._fields(finish, "c0")["conditional_doppler_rms_hz"] == 70.0


def test_separate_chart_rosters_and_missing_terminal_status(tmp_path):
    plan = dict(
        cohorts={"confirmation": ["DS26-0012"], "stress": ["DS26-0152"]},
        bindings={"DS26-0012": {"id": "DS26-0012"}},
    )
    figures = results._figure_spec(plan)
    assert [chart["cases"] for chart in figures["charts"]] == [["DS26-0012"], ["DS26-0152"]]
    assert [chart["seal"] for chart in figures["charts"]] == [
        "confirmation-lock.json",
        "stress-lock.json",
    ]
    row = results._candidate(tmp_path, plan, "DS26-0012", "confirmation")
    assert row["result"]["status"] == "missing" and row["worker_wall_s"] is None
    (tmp_path / "DS26-0012").mkdir()
    assert (
        results._candidate(tmp_path, plan, "DS26-0012", "confirmation")["result"]["status"]
        == "failed"
    )
