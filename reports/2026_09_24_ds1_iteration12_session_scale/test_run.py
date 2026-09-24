from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest


def module():
    path = Path(__file__).with_name("run.py")
    spec = importlib.util.spec_from_file_location("iteration12_test", path)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


def test_lattice_is_symmetric_and_keeps_the_sealed_center():
    m = module()
    center = {"latitude_deg": 37.0, "longitude_deg": -122.0}
    rows = m.lattice(center)
    assert len(rows) == 9
    assert {
        (row["east_km_from_iteration10"], row["north_km_from_iteration10"]) for row in rows
    } == {
        (east, north)
        for east in (-m.LOCAL_SPACING_KM, 0.0, m.LOCAL_SPACING_KM)
        for north in (-m.LOCAL_SPACING_KM, 0.0, m.LOCAL_SPACING_KM)
    }


def test_scale_block_recovers_common_and_session_terms_after_track_cfo_profile():
    m = module()
    base = np.concatenate(
        [np.linspace(-1_000_000.0, 1_000_000.0, 500), np.linspace(-900_000.0, 1_100_000.0, 500)]
    )
    session_index = np.repeat([0, 1], 500)
    track_index = np.repeat([0, 1], 500)
    true_scale = np.array([1.3e-4, 2.2e-4, -1.7e-4])
    multiplier = 1.0 + true_scale[0] + true_scale[1:][session_index]
    # The arbitrary track offsets establish that this is really a
    # track-CFO-profiled recovery rather than a raw-amplitude fit.
    y = multiplier * base + np.repeat([9.0, -11.0], 500)

    class Synthetic:
        session_names = np.array(["s0", "s1"])
        track_names = np.array(["t0", "t1"])

        def __init__(self):
            self.session_index = session_index
            self.track_index = track_index

        def residual(self, _rates, scale):
            raw = y - (1.0 + scale[0] + scale[1:][session_index]) * base
            return m._center(raw, track_index, len(self.track_names)), base, raw

    fitted, status = m._fit_scales(Synthetic(), np.zeros(1), np.zeros(3))
    assert status["converged"]
    # The common/deviation parameterization has a prior-determined gauge, but
    # its two session totals are directly observable and must be recovered.
    assert fitted[0] + fitted[1] == pytest.approx(true_scale[0] + true_scale[1], abs=5e-7)
    assert fitted[0] + fitted[2] == pytest.approx(true_scale[0] + true_scale[2], abs=5e-7)


def test_capped_loss_is_track_weighted_not_sample_weighted():
    m = module()
    error = np.array([0.0, 800.0, 400.0])
    track = np.array([0, 0, 1])
    names = np.array(["long", "short"])
    assert m._capped_loss(error, track, names, {"long": 2, "short": 1}) == pytest.approx(
        (2 * 0.5 + 1 * 0.25) / 3
    )


def test_scale_contract_is_regularized_and_guarded():
    m = module()
    assert m.COMMON_SCALE_SIGMA == m.SESSION_SCALE_SIGMA == 5e-4
    assert m.SCALE_BOUND == 0.002
    assert m.SCALE_BOUND > 3 * m.COMMON_SCALE_SIGMA
    assert m.MAX_OUTER_ITERATIONS == 16
