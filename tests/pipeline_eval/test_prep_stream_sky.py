from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from leo.sky.propagation import ElementSetCatalogue
from tools.pipeline_eval.variants import prep_stream_sky, v5_catalogue_memory


def catalogue(count):
    rows = tuple(range(count))
    return ElementSetCatalogue(
        tuple(f"STARLINK {n}" for n in rows), tuple(100_000 - n for n in rows), rows
    )


def test_regional_blocks_keep_all_eligible_rows_in_source_order_and_exact_fine_states():
    src = catalogue(4 * prep_stream_sky.COARSE_ROWS + 16)
    calls = []

    def states(cat, origin, times):
        ids = np.asarray(cat.satellites)
        calls.append((len(ids), len(times)))
        position = (ids[:, None, None] + (np.arange(3) + times[:, None] / 100) / 1e3).astype(float)
        return position, -position / 5, ids % 11 != 9

    def look(position, velocity, site, rotation):
        ids = np.rint(position[:, :, 0]).astype(int)
        angle = np.where(ids % 7 == 2, -12.000001, -12.0)
        return angle * 0, angle, angle * 0, angle * 0

    kernel = SimpleNamespace(
        ElementSetCatalogue=ElementSetCatalogue,
        ecef_states=states,
        look_angles=look,
        geodetic_to_ecef_km=lambda *a: a,
        ecef_to_enu_matrix=lambda *a: a,
    )
    usage = Counter()
    duration = 304.1
    actual = prep_stream_sky.regional_bank(
        kernel, usage, src, 17, duration, screen_latitude_deg=31, screen_longitude_deg=-105
    )
    coarse, fine = np.arange(0.0, duration + 5, 5), np.arange(-17.0, np.ceil(duration) + 18)
    assert all(n <= prep_stream_sky.COARSE_ROWS for n, t in calls if t == len(coarse))
    assert all(n <= v5_catalogue_memory.SATELLITES_PER_BATCH for n, t in calls if t == len(fine))
    p, v, good = states(src, 17, coarse)
    expected = np.flatnonzero(good & (look(p, v, None, None)[1].max(axis=1) >= -12))
    np.testing.assert_array_equal(actual["source_indices"], expected)
    assert actual["catalogue"].satellite_numbers == tuple(
        src.satellite_numbers[k] for k in expected
    )
    p, v, _ = states(actual["catalogue"], 17, fine)
    np.testing.assert_array_equal(p, actual["bank"]["position_km"])
    np.testing.assert_array_equal(v, actual["bank"]["velocity_km_s"])
    assert usage["retained_state_bytes"] == p.nbytes + v.nbytes


def test_empty_or_unusable_regional_bank_preserves_frozen_errors():
    def states(cat, origin, knots):
        vectors = np.zeros((len(cat), len(knots), 3))
        return vectors, vectors, np.full(len(cat), len(knots) < 100, dtype=bool)

    kernel = SimpleNamespace(
        ElementSetCatalogue=ElementSetCatalogue,
        ecef_states=states,
        geodetic_to_ecef_km=lambda *a: a,
        ecef_to_enu_matrix=lambda *a: a,
        look_angles=lambda p, *a: tuple(np.zeros(p.shape[:2]) for _ in range(4)),
    )
    for src, duration, message in (
        (catalogue(0), 300.0, "no regional causal candidates"),
        (catalogue(2), 300.0, "causal state bank propagation failed"),
        (catalogue(2), np.nan, "Finite nonnegative"),
    ):
        with pytest.raises(ValueError, match=message):
            prep_stream_sky.regional_bank(
                kernel, Counter(), src, 0, duration, screen_latitude_deg=42, screen_longitude_deg=2
            )
