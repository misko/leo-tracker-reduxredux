from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import orbit_modes, orbits
from leo.sky.propagation import ElementSetCatalogue
from tools.pipeline_eval.variants import v5_core
from tools.pipeline_eval.variants.experimental import regional_reassignment as guard

trial = import_module("reports.ALGO08.single-core-2x.oracle_orbit_solve_trial")


def bank():
    position = np.arange(18.0).reshape(3, 2, 3)
    return dict(
        time_s=np.array([0, 1]),
        norad=np.array([23, 11, 15]),
        phase_sigma_s=np.array([1.0, 2.0, 3.0]),
        position_km=position,
        velocity_km_s=position + 100,
    )


def propagated(catalogue, _origin, times):
    p = np.full((len(catalogue.satellite_numbers), len(times), 3), 200.0)
    return p, p + 100, np.ones(len(p), bool)


def test_all_matched_rows_replaced_and_unmatched_rows_keep_causal_states(monkeypatch):
    monkeypatch.setattr(orbits, "ecef_states", propagated)
    raw = bank()
    before = raw["position_km"].copy()
    original, oracle = trial.sky_pair(
        raw, 2, {11: object(), 15: object(), 800: object()}, use_oracle=True, intersection=False
    )
    assert original is raw and oracle["norad"] is raw["norad"]
    assert oracle["time_s"] is raw["time_s"] and oracle["phase_sigma_s"] is raw["phase_sigma_s"]
    np.testing.assert_array_equal(raw["position_km"], before)
    np.testing.assert_array_equal(oracle["position_km"][0], before[0])
    np.testing.assert_array_equal(oracle["position_km"][1:], 200.0)
    np.testing.assert_array_equal(oracle["velocity_km_s"][1:], 300.0)


def test_common_intersection_is_identical_for_causal_and_oracle_eligibility(monkeypatch):
    monkeypatch.setattr(orbits, "ecef_states", propagated)
    raw = bank()
    generator = {23: object(), 15: object(), 800: object()}
    _, control = trial.sky_pair(raw, 2, generator, use_oracle=False, intersection=True)
    prior, oracle = trial.sky_pair(raw, 2, generator, use_oracle=True, intersection=True)
    for key in ("norad", "time_s", "phase_sigma_s"):
        np.testing.assert_array_equal(control[key], oracle[key])
    np.testing.assert_array_equal(oracle["norad"], [23, 15])
    np.testing.assert_array_equal(control["position_km"], prior["position_km"])
    np.testing.assert_array_equal(oracle["position_km"], 200.0)


def test_unusable_propagation_cannot_silently_change_oracle_roster(monkeypatch):
    def fail(catalogue, origin, times):
        p, v, good = propagated(catalogue, origin, times)
        good[-1] = False
        return p, v, good

    monkeypatch.setattr(orbits, "ecef_states", fail)
    with pytest.raises(RuntimeError, match="unusable ORACLE states"):
        trial.sky_pair(bank(), 2, {23: object()}, use_oracle=True, intersection=False)


def test_scan_prior_routes_keep_causal_geometry_and_original_element_records(monkeypatch):
    monkeypatch.setattr(orbits, "ecef_states", propagated)
    raw = bank()
    elements = {"23": {"collected_utc_ns": 9}}

    def make_scan(prepared, _region, _sha, _bound, _previous):
        sky = prepared["sky"]
        assert sky["nominal_elements"] is elements
        return SimpleNamespace(sky=sky["bank"], elements=elements)

    def widths(scan, labels):
        assert scan.sky is raw and scan.elements is elements
        return labels

    monkeypatch.setattr(v5_core, "scan_context", make_scan)
    monkeypatch.setattr(orbit_modes, "previous_bank", widths)
    prepared = dict(
        sky=dict(
            bank=raw, nominal_elements=elements, metadata={"cutoff_utc_ns": 10, "origin_utc_ns": 11}
        )
    )
    with trial.trial_geometry({23: object()}, True, False, {}) as _:
        scan = v5_core.scan_context(prepared, None, None, None, None)
        assert scan.sky is not raw and scan.elements is elements
        np.testing.assert_array_equal(scan.sky["position_km"][0], 200.0)
        assert orbit_modes.previous_bank(scan, [0]) == [0]
    assert v5_core.scan_context is make_scan and orbit_modes.previous_bank is widths


def test_guard_preserves_causal_prefilter_and_uses_oracle_fine_states(monkeypatch):
    catalogue = ElementSetCatalogue(("a", "b", "c"), (23, 11, 15), (1, 2, 3))
    generator = {23: 10, 15: 30}
    dates = np.array([0.0, 1.0])

    def stock(catalogue, _origin, times):
        return (
            np.full((len(catalogue), len(times), 3), 70.0),
            np.full((len(catalogue), len(times), 3), 80.0),
            np.ones(len(catalogue), bool),
        )

    def geometry(catalogue, *_a, **_kw):
        coarse, _, _ = guard.ecef_states(catalogue, 0, dates)
        np.testing.assert_array_equal(coarse, 70.0)
        fine, _, _ = guard.ecef_states(catalogue, 0, dates)
        np.testing.assert_array_equal(fine[:, 0, 0], [200.0, 70.0, 200.0])
        return "geometry"

    def evaluate(_tracks, active, _region):
        assert active is catalogue
        return guard.orbit_geometry(active)

    monkeypatch.setattr(orbits, "ecef_states", propagated)
    monkeypatch.setattr(guard, "ecef_states", stock)
    monkeypatch.setattr(guard, "orbit_geometry", geometry)
    monkeypatch.setattr(guard, "evaluate_veto", evaluate)
    trace = {}
    with trial.trial_geometry(generator, True, False, trace):
        assert guard.evaluate_veto(None, catalogue, None) == "geometry"
    assert trace == {
        "guard_input_count": 3,
        "guard_state_rosters": [3, 3],
        "guard_fine_missing": [11],
    }
    assert guard.ecef_states is stock and guard.orbit_geometry is geometry
