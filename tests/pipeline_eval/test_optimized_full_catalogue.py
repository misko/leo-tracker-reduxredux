from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def research(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module


def test_exterior_handoff_requires_same_prepared_tracks_root_and_cutoff(research, tmp_path):
    from prepared_exterior import PreparedExterior

    catalogue = object()
    tracks = dict(metadata=dict(causal_cutoff_utc_ns=42))
    reader = SimpleNamespace(root=tmp_path)
    prepared = PreparedExterior(reader.root, tracks, 42, catalogue)
    assert prepared.match(tracks, reader) is catalogue
    assert prepared.match(dict(tracks), reader) is None
    assert prepared.match(tracks, SimpleNamespace(root=tmp_path / "other")) is None
    tracks["metadata"]["causal_cutoff_utc_ns"] += 1
    assert prepared.match(tracks, reader) is None


def test_reduced_grid_scopes_optimization_and_preserves_stock_fallback(research, monkeypatch):
    from leo.presentation import localization_v3
    from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

    grid = research("optimized_grid")
    monkeypatch.setattr(handoff, "predictive_factor", lambda _: "stock")
    monkeypatch.setattr(localization_v3, "sample_position_grid", lambda factors: [handoff.predictive_factor(f) for f in factors])

    def reduced(factor, *, include_residual):
        assert include_residual
        if factor == "invalid":
            raise ValueError("Unsupported groups")
        return "reduced", dict(prefix=2, biases=4)

    monkeypatch.setattr(grid, "reduced_predictive", reduced)
    with grid.reduced_grid() as counts:
        assert handoff.predictive_factor("valid") == "stock"
        assert localization_v3.sample_position_grid(["valid", "invalid"]) == ["reduced", "stock"]
        assert handoff.predictive_factor("valid") == "stock"
    assert counts["grid_calls"] == counts["reduced_calls"] == counts["original_fallback_calls"] == 1
    assert counts["collapsed_biases"] == 4
    assert localization_v3.sample_position_grid(["valid"]) == ["stock"]


def test_grid_comparison_ignores_only_binding_timing_and_scores(research):
    trial = research("optimized_full_catalogue_trial")
    original = dict(complete=True, binding="old", elapsed_seconds=1., region_center=[1., 2.], points=[
        dict(east_km=0., north_km=0., scores=dict(c0=40., fitted_c=22.)),
        dict(east_km=1., north_km=0., scores=dict(c0=8., fitted_c=29.)),
    ])
    reference, changed = original["points"]
    candidate = dict(original, binding="fresh", elapsed_seconds=2., points=[
        reference, dict(changed, scores=dict(c0=8.000000001, fitted_c=29.))])
    checks = trial.grid_errors(original, candidate)
    assert checks["equal_metadata"] and checks["equal_coordinates"] and checks["complete"]
    assert checks["minima"] == dict(c0=[1, 1], fitted_c=[0, 0])
    assert checks["max_abs_error"]["c0"] == pytest.approx(1e-9, abs=1e-15)
    assert not trial.grid_errors(original, dict(candidate, points=candidate["points"][::-1]))["equal_coordinates"]
