"""Prove that family confidence needs only the original alignment samples."""

import hashlib
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.variants import v5_family_memory as fast


@pytest.fixture
def orbit_inventory(monkeypatch):
    calls = []
    old_numbers = (10, 30)
    modules = ModuleType("leo.analysis.localization_v3")

    def earlier(catalogue, _origin, epochs):
        calls.append(epochs.tolist())
        n = np.asarray(catalogue.satellite_numbers)
        p = np.column_stack((2 * n + n / 10, np.zeros(len(n)), np.zeros(len(n))))
        return (
            np.repeat(p[:, None, :], len(epochs), axis=1),
            np.zeros((len(n), len(epochs), 3)),
            np.ones(len(n), dtype=bool),
        )

    def samples(bank, epochs, phase):
        assert phase == 0
        indexes = np.searchsorted(bank["time_s"], epochs)
        return bank["position_km"][:, indexes], bank["velocity_km_s"][:, indexes]

    modules.orbit_modes = SimpleNamespace(
        EARTH_ROTATION_RAD_S=0.01,
        parse_element_sets=lambda _: SimpleNamespace(
            satellite_numbers=old_numbers, satellites=[1, 2]
        ),
        ElementSetCatalogue=lambda _, numbers, _sat: SimpleNamespace(satellite_numbers=numbers),
        ecef_states=earlier,
        phase_shifted_states=samples,
    )
    monkeypatch.setitem(sys.modules, modules.__name__, modules)
    numbers = np.array([10, 20, 30])
    time = np.arange(301.0)
    p = np.column_stack((2 * numbers, np.zeros(3), np.zeros(3)))
    v = np.column_stack((np.ones(3), -0.01 * p[:, 0], np.zeros(3)))
    previous = "pinned earlier elements"
    scan = SimpleNamespace(
        sky=dict(
            time_s=time,
            position_km=np.repeat(p[:, None, :], len(time), axis=1),
            velocity_km_s=np.repeat(v[:, None, :], len(time), axis=1),
        ),
        norads=numbers,
        previous_tle=previous,
        origin_utc_ns=10,
        previous_tle_sha256=hashlib.sha256(previous.encode()).hexdigest(),
        previous_shape_cache={},
    )
    return scan, calls


def test_full_and_reordered_prior_alignment_preserve_order_and_missing_elements(orbit_inventory):
    scan, calls = orbit_inventory
    a = fast.alignment_only(scan, [0, 1, 2])
    b = fast.alignment_only(scan, [2, 1, 0])
    assert a == (None, {0, 2}, {10: 1.0, 30: 3.0})
    assert b == (None, {0, 2}, {30: 3.0, 10: 1.0})
    assert calls == [[0.0, 150.0, 300.0]] * 2
    assert scan.previous_shape_cache == {}


def test_prior_scope_preserves_preexisting_bank_and_checks_causal_bytes(orbit_inventory):
    scan, calls = orbit_inventory
    previous = (scan.sky, {0}, {10: 1.0})
    scan.previous_shape_cache[(0,)] = previous
    assert fast.alignment_only(scan, [0]) is previous
    assert fast.alignment_only(scan, [1]) == (None, set(), {})
    assert calls == []
    scan.previous_tle += " changed"
    with pytest.raises(ValueError, match="causal TLE bytes differ"):
        fast.alignment_only(scan, [0])
