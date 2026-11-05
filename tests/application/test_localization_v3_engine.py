from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.region import SearchRegion
from leo.application import localization_v3_engine as engine

FUNCTIONS = [
    ("fit_initial_position", "initial_position_fitted", "initial_fit"),
    ("refit_initial_position", "conservative_fit_evaluated", "conservative_fit"),
    ("fit_family_policy", "family_policy_evaluated", "family_fit"),
    ("fit_signed_policy", "signed_policy_evaluated", "signed_context"),
    ("fit_family_cavity", "family_cavity_evaluated", "cavity_fit"),
    ("prepare_track_recovery", "track_recovery_prepared", "inventory"),
    ("recover_predictive_checkpoint", "predictive_recovery_evaluated", "recovery"),
    ("recover_numerical_checkpoint", "numerical_recovery_evaluated", "recovery"),
    ("recover_gap_checkpoint", "gap_recovery_evaluated", "recovery"),
    ("prepare_additional_checkpoint", "additional_recovery_prepared", "residual_context"),
    ("screen_additional_recovery", "additional_candidates_screened", "screen"),
    ("fit_additional_recovery", "additional_position_evaluated", "recovery"),
    ("prepare_reassociation", "reassociation_prepared", None),
    ("rank_reassociation_families", "reassociation_targets_ranked", "ranking"),
    ("screen_reassociation_candidates", "reassociation_candidates_screened", "admission"),
    ("fit_reassociation", "reassociation_evaluated", "recovery"),
]


def test_initial_executor_port_is_forwarded_only_to_initial_search(monkeypatch):
    from dataclasses import replace

    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    def mapper(operation, arms):
        return list(map(operation, arms))
    execution = replace(execution, map_initial_arms=mapper)
    engine.infer_prepared(prepared, region, catalogue, identities=['scan'],
                          collect_history=object(), execution=execution)
    for name, _, kwargs in calls:
        if name == 'fit_initial_position':
            assert kwargs['map_arms'] is mapper
        else:
            assert 'map_arms' not in kwargs


def test_family_executor_is_scoped_to_family_policy(monkeypatch):
    from dataclasses import replace

    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    mapper = object()
    execution = replace(execution, map_family_arms=mapper)
    engine.infer_prepared(prepared, region, catalogue, identities=['scan'],
                          collect_history=object(), execution=execution)
    for name, _, kwargs in calls:
        if name == 'fit_family_policy':
            assert kwargs['map_arms'] is mapper
        else:
            assert 'map_arms' not in kwargs


def test_fold_executor_is_scoped_to_predictive_checkpoint(monkeypatch):
    from dataclasses import replace

    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    mapper = object()
    execution = replace(execution,map_predictive_folds=mapper)
    engine.infer_prepared(prepared,region,catalogue,identities=['scan'],
                          collect_history=object(),execution=execution)
    for name, _, kwargs in calls:
        if name == 'recover_predictive_checkpoint':
            assert kwargs['map_annotation_folds'] is mapper
        else:
            assert 'map_annotation_folds' not in kwargs


def test_recovery_arm_executor_is_scoped_to_original_predictive_checkpoint(monkeypatch):
    from dataclasses import replace

    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    mapper = object()
    execution = replace(execution, map_recovery_arms=mapper)
    engine.infer_prepared(prepared, region, catalogue, identities=['scan'],
                          collect_history=object(), execution=execution)
    for name, _, kwargs in calls:
        if name == 'recover_predictive_checkpoint':
            assert kwargs['map_inclusion_arms'] is mapper
        else:
            assert 'map_inclusion_arms' not in kwargs


def fixture(monkeypatch, *, selected=False, fault=None):
    region = SearchRegion((37.906, -122.545))
    prepared = dict(
        status="inputs_prepared",
        sky=dict(metadata=dict(cutoff_utc_ns=123)),
        tracks=dict(observations=["native"], tracks=["graph"]),
        noise={},
    )
    catalogue = dict(cutoff_utc_ns=123)
    owners = {a: {"native": 2 if selected else 1} for a in ("c0", "fitted_c")}
    arms = {a: dict(proposed_owners=o) for a, o in owners.items()}
    context = dict(
        scan=SimpleNamespace(search_region=region),
        problems={a: (object(), np.array([1.0, 2.0])) for a in owners},
    )
    calls, results = [], {}

    def make(name, status, field):
        def call(*args, **kwargs):
            calls.append((name, args, kwargs))
            value = dict(status=status)
            if field is not None:
                value[field] = {"stage": name}
            if name == "prepare_reassociation":
                value.update(context=context, arms=arms, owners=owners)
            if name == "fit_reassociation":
                value.update(
                    recovery_complete=True,
                    recovery=dict(
                        selected="repair" if selected else None,
                        final={a: dict(x=[1.0, 2.0], associated=1) for a in owners},
                    ),
                )
                if selected:
                    kwargs["on_selected"](context, arms)
            if name == fault:
                value["status"] = "failed"
            results[name] = value
            return value

        return call

    for name, status, field in FUNCTIONS:
        monkeypatch.setattr(engine.policy, name, make(name, status, field))
    ticks = iter(range(100))
    execution = engine.ExecutionPorts(
        run_stage=object(),
        run_gap_stage=object(),
        discovery_allowed=object(),
        charge_reused=object(),
        clock=lambda: next(ticks),
    )
    return prepared, region, catalogue, execution, calls, results, context, owners


@pytest.mark.parametrize("selected", [False, True])
def test_runner_preserves_order_selected_state_and_execution_ports(monkeypatch, selected):
    prepared, region, catalogue, execution, calls, results, context, owners = fixture(
        monkeypatch, selected=selected
    )
    collect, events = object(), []
    result = engine.infer_prepared(
        prepared,
        region,
        catalogue,
        identities=["scan"],
        collect_history=collect,
        execution=execution,
        on_stage=events.append,
    )
    assert [name for name, _, _ in calls] == [row[0] for row in FUNCTIONS]
    assert result["status"] == "numerics_complete"
    assert result["context"] is context and result["owners"] == owners
    assert len(events) == 16 and all(row["seconds"] == 1 for row in events)
    events[0]["seconds"] = 999
    assert result["stage_timings"][0]["seconds"] == 1
    by_name = {name: (args, kw) for name, args, kw in calls}
    assert by_name["refit_initial_position"][0][1] is results["fit_initial_position"]["initial_fit"]
    assert (
        by_name["fit_family_policy"][0][1] is results["refit_initial_position"]["conservative_fit"]
    )
    assert by_name["fit_signed_policy"][0][2] is results["fit_family_policy"]["family_fit"]
    assert by_name["recover_predictive_checkpoint"][1]["run_stage"] is execution.run_stage
    assert by_name["recover_numerical_checkpoint"][1]["charge_reused"] is execution.charge_reused
    assert by_name["recover_gap_checkpoint"][1]["run_stage"] is execution.run_gap_stage
    assert by_name["recover_gap_checkpoint"][1]["maximum_seconds"] == 1200
    assert by_name["fit_reassociation"][0][-1] is collect
    assert all("evaluation_reference" not in kw for _, _, kw in calls)


@pytest.mark.parametrize("fault", [row[0] for row in FUNCTIONS])
def test_incomplete_stage_never_advances_to_later_policy(monkeypatch, fault):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch, fault=fault)
    with pytest.raises(engine.IncompleteStage):
        engine.infer_prepared(
            prepared,
            region,
            catalogue,
            identities=["scan"],
            collect_history=object(),
            execution=execution,
        )
    assert calls[-1][0] == fault


def test_catalogue_cutoff_is_checked_before_any_fit(monkeypatch):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    catalogue["cutoff_utc_ns"] += 1
    with pytest.raises(ValueError, match="cutoffs"):
        engine.infer_prepared(
            prepared,
            region,
            catalogue,
            identities=["scan"],
            collect_history=object(),
            execution=execution,
        )
    assert not calls


def test_native_no_curvature_does_not_read_recovery_catalogue_or_render(monkeypatch):
    monkeypatch.setattr(
        engine.policy, "prepare_native_scan", lambda *a, **k: dict(status="no_active_curvature")
    )
    monkeypatch.setattr(
        engine.policy, "prepare_additional_catalogue", lambda *a: pytest.fail("archive read")
    )
    ticks = iter(range(10))
    execution = SimpleNamespace(clock=lambda: next(ticks))
    result = engine.run_native(
        {},
        object(),
        object(),
        object(),
        identities=["scan"],
        execution=execution,
        screen_latitude_deg=1.0,
        screen_longitude_deg=2.0,
        title="scan",
    )
    assert result["status"] == "no_active_curvature" and result["products"] == {}


def test_native_route_never_passes_evaluation_reference_into_inference(monkeypatch):
    reference = dict(latitude_deg=10.0, longitude_deg=20.0)
    prepared = dict(status="inputs_prepared", sky=dict(bank={}, metadata=dict(cutoff_utc_ns=123)))
    monkeypatch.setattr(engine.policy, "prepare_native_scan", lambda *a, **kw: prepared)
    monkeypatch.setattr(
        engine.policy, "prepare_additional_catalogue", lambda *a: {"catalogue": True}
    )
    monkeypatch.setattr(
        engine.policy, "prepare_reassociation_history", lambda *a: pytest.fail("eager history")
    )
    seen = []

    def infer(*args, **kw):
        assert args[0] == prepared and "evaluation_reference" not in kw
        seen.append("infer")
        return dict(status="numerics_complete")

    def render(value, **kw):
        assert seen == ["infer"] and kw["evaluation_reference"] is reference
        return dict(status="figures_ready", products={"png": b"bytes"}, stage_timings=[])

    monkeypatch.setattr(engine, "infer_prepared", infer)
    monkeypatch.setattr(engine, "render_inference", render)
    ticks = iter(range(10))
    result = engine.run_native(
        {},
        object(),
        object(),
        object(),
        identities=["scan"],
        execution=SimpleNamespace(clock=lambda: next(ticks)),
        screen_latitude_deg=1.0,
        screen_longitude_deg=2.0,
        title="scan",
        evaluation_reference=reference,
    )
    assert result["status"] == "figures_ready" and len(result["stage_timings"]) == 2


def test_incomplete_final_work_is_not_complete(monkeypatch):
    prepared, region, catalogue, execution, *_ = fixture(monkeypatch)
    original = engine.policy.fit_reassociation

    def incomplete(*a, **k):
        result = original(*a, **k)
        result["recovery_complete"] = False
        result["recovery"]["execution_status"] = "incomplete"
        return result

    monkeypatch.setattr(engine.policy, "fit_reassociation", incomplete)
    with pytest.raises(engine.IncompleteStage, match="final"):
        engine.infer_prepared(
            prepared,
            region,
            catalogue,
            identities=["scan"],
            collect_history=object(),
            execution=execution,
        )


def test_stage_timing_rejects_clock_regression():
    ticks = iter([2.0, 1.0])
    timer = engine._Timing(lambda: next(ticks), None)
    with pytest.raises(ValueError, match="monotonic"):
        timer.run("stage", lambda: {})


def test_native_materialization_preserves_recorded_types_without_copying_orbit_bank():
    bank = dict(position_km=np.arange(6.0).reshape(2, 3))
    prepared = dict(
        status="inputs_prepared",
        sky=dict(bank=bank),
        tracks=dict(times=np.array([1.0, 2.0]), degree=np.int64(3)),
        noise=dict(selected=np.bool_(True)),
    )
    result = engine._prepared_values(prepared)
    assert result["sky"]["bank"] is bank
    assert result["tracks"] == dict(times=[1.0, 2.0], degree=3)
    assert type(result["tracks"]["degree"]) is int
    assert result["noise"]["selected"] is True
    result["tracks"]["times"][0] = 100.0
    assert prepared["tracks"]["times"][0] == 1.0


@pytest.mark.parametrize("fault", ["missing", "position", "ownership"])
def test_stale_final_selection_cannot_leave_the_engine(monkeypatch, fault):
    prepared, region, catalogue, execution, *_ = fixture(monkeypatch, selected=True)
    original = engine.policy.fit_reassociation

    def bad(*args, **kwargs):
        if fault == "missing":
            kwargs["on_selected"] = lambda *a: None
        value = original(*args, **kwargs)
        if fault == "position":
            value["recovery"]["final"]["c0"]["x"][0] += 1.0
        if fault == "ownership":
            value["recovery"]["final"]["fitted_c"]["associated"] += 1
        return value

    monkeypatch.setattr(engine.policy, "fit_reassociation", bad)
    with pytest.raises(ValueError):
        engine.infer_prepared(
            prepared,
            region,
            catalogue,
            identities=["scan"],
            collect_history=object(),
            execution=execution,
        )


def test_render_boundary_has_separate_timing_and_is_only_reference_consumer(monkeypatch):
    from leo.presentation import fast_standard_analysis, localization_v3, localization_v3_path

    prepared, region, catalogue, execution, *_ = fixture(monkeypatch)
    result = engine.infer_prepared(
        prepared,
        region,
        catalogue,
        identities=["scan"],
        collect_history=object(),
        execution=execution,
    )
    path = dict(selected_model="selected")
    monkeypatch.setattr(localization_v3_path, "recorded_decision_path", lambda *a, **k: path)
    seen = []

    def prepare(context, owners, arms, observations, tracks, **kwargs):
        assert context is result["context"] and owners is result["owners"]
        assert observations is result["native"]["observations"]
        assert kwargs["position_path"] is path and "evaluation_reference" not in kwargs
        seen.append("grid")
        return dict(marker="complete plot evidence")

    reference = dict(latitude_deg=10.0, longitude_deg=20.0)

    def render(packet, **kwargs):
        assert seen == ["grid"] and packet["marker"] == "complete plot evidence"
        assert kwargs["evaluation_reference"] is reference
        seen.append("render")
        return dict(figure=b"png")

    monkeypatch.setattr(localization_v3, "prepare_packet", prepare)
    monkeypatch.setattr(fast_standard_analysis, "render", render)
    rendered = engine.render_inference(
        result, title="scan", clock=execution.clock, evaluation_reference=reference
    )
    assert seen == ["grid", "render"] and rendered["status"] == "figures_ready"
    assert [r["stage"] for r in rendered["stage_timings"][-2:]] == [
        "plot_evidence",
        "png_rendering",
    ]
