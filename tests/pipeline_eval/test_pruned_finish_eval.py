import sys
from types import ModuleType, SimpleNamespace

from tools.pipeline_eval.qualification import pruned_finish_eval as study


def sample():
    metrics = dict(
        checked_residual_addition={"status": "no_qualified_new_family"},
        addition_status="no_qualified_new_family",
        reassociation_selected=None,
        reassociation_targets=[18],
        reassociation_admitted=0,
        residual_targets=3,
        ordered_phase_seeds={"aligned": [], "equal_length": 0},
        native_observations=100,
        tracks=20,
        measured_finish={"eligible_scores": [{"norad": 18, "rank_score": 1.0}]},
    )
    for arm in study.ARMS:
        metrics[f"{arm}_associated_observations"] = 80
        metrics[f"{arm}_frequency_score"] = 42.0
    return dict(
        qualification="fresh",
        result=dict(
            status="ok",
            arms={a: {"latlon": [1, 2]} for a in study.ARMS},
            metrics=metrics,
        ),
    )


def test_parity_rejects_rms_objective_and_eligible_ranking_drift_independently():
    a, b = sample(), sample()
    assert study.verify_science(a, b)["exact"]
    a["result"]["metrics"]["c0_conditional_rms_hz"] = 70.0
    verdict = study.verify_science(a, b)
    assert verdict["endpoint"] and verdict["objective"]["c0"] and not verdict["rms"]["c0"]
    b["result"]["metrics"]["c0_conditional_rms_hz"] = 70.0
    a["result"]["metrics"]["c0_frequency_score"] += 1.0
    assert not study.verify_science(a, b)["objective"]["c0"]
    a["result"]["metrics"]["c0_frequency_score"] -= 1.0
    a["result"]["metrics"]["measured_finish"]["eligible_scores"][0]["rank_score"] = 2.0
    assert not study.verify_science(a, b)["eligible_scores"]
    b["qualification"] = "historical_control"
    assert study.verify_science(a, b)["eligible_scores"] is None


def test_noncompleted_rows_are_not_reported_as_exact_matches():
    a, b = sample(), sample()
    a["result"]["status"] = "timed_out"
    assert study.verify_science(a, b) == {"compared": False, "exact": False}


def test_finish_observer_counts_actual_operations_inside_installed_hooks(monkeypatch):
    loc = ModuleType("leo.analysis.localization_v3")
    application = ModuleType("leo.application")
    loc.residual_preflight = SimpleNamespace(preflight=lambda: None)
    loc.residual_screen = SimpleNamespace(_nomination_grids=lambda: None, ecef_states=lambda: None)
    loc.reassociation_context = SimpleNamespace(build=lambda **kwargs: None)
    loc.additional_recovery = SimpleNamespace(recover_additional=lambda: None)
    application.localization_v3 = SimpleNamespace(
        screen_reassociation_candidates=lambda: None,
        fit_reassociation=lambda: None,
    )
    monkeypatch.setitem(sys.modules, loc.__name__, loc)
    monkeypatch.setitem(sys.modules, application.__name__, application)
    rows = [
        dict(norad=3, points=30, tracks=2, rank_score=0.8),
        dict(norad=8, points=20, tracks=1, rank_score=1.2),
    ]

    def screen():
        loc.residual_screen.ecef_states()
        loc.residual_screen._nomination_grids()
        loc.residual_screen._nomination_grids()

    def rank(context):
        for item in rows:
            loc.reassociation_context.build(omit=item["norad"])
        return rows, [3]

    loc.residual_screen.screen_candidates = screen
    loc.reassociation_context.rank_families = rank

    def finish():
        loc.residual_screen.screen_candidates()
        return loc.reassociation_context.rank_families({})

    observed = {}
    assert study.observe_finish(finish, observed) == (rows, [3])
    assert observed["work"] == {"arm_omissions": 2, "nomination_grids": 2, "ecef_states": 1}
    assert observed["eligible_scores"] == [rows[0]]
    assert observed["selected"] == [3]
    assert observed["stages"].keys() == {"ranking", "residual_screen"}
    assert loc.residual_screen.screen_candidates is screen
    assert loc.reassociation_context.rank_families is rank
