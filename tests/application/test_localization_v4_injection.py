from dataclasses import replace
from types import SimpleNamespace

from leo.application import localization_v3 as policy
from leo.application import localization_v3_engine as engine
from tests.application.test_localization_v3_engine import fixture


def test_engine_threads_bound_to_every_scan_creation_policy(monkeypatch):
    prepared, region, catalogue, execution, calls, *_ = fixture(monkeypatch)
    bound = object()
    engine.infer_prepared(
        prepared, region, catalogue, identities=["scan"], collect_history=object(),
        execution=replace(execution, bound=bound),
    )
    creators = {"fit_initial_position", "refit_initial_position", "fit_family_policy",
                "fit_signed_policy"}
    assert {name for name, _, kw in calls if kw.get("bound") is bound} == creators


def test_all_context_wrappers_construct_scans_with_the_explicit_bound(monkeypatch):
    bound, region, calls = object(), object(), []
    receipt = dict(catalogue_sha256="digest", sources={})
    prepared = dict(
        status="inputs_prepared", tracks=dict(tracks=[], observations=[]), noise={},
        sky=dict(bank={}, nominal_elements={}, previous_receipt=receipt,
                 genuine_previous_receipt=receipt, previous_tle="old",
                 genuine_previous_tle="genuine", metadata=dict(origin_utc_ns=0,
                 regional_center=[0., 0.], cutoff_utc_ns=0)),
        phase_history={}, phase_forecast={},
    )

    def scan(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(radio_sigma_hz=150.)

    monkeypatch.setattr(policy, "ScanLikelihood", scan)
    for method in ("initial_search", "conservative_recovery", "history_policy", "signed_context"):
        monkeypatch.setattr(policy, method, lambda *args, **kwargs: {})
    policy.fit_initial_position(prepared, region, bound=bound)
    policy.refit_initial_position(prepared, {}, region, bound=bound)
    policy.fit_family_policy(prepared, {}, region, bound=bound)
    policy.fit_signed_policy(prepared, {}, {}, region, bound=bound)
    assert len(calls) == 4
    assert all(row["bound"] is bound and row["search_region"] is region for row in calls)
    assert [row["previous_tle"] for row in calls] == ["old", "genuine", "genuine", "genuine"]
