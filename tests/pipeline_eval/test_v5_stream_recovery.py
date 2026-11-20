from contextlib import ExitStack
from dataclasses import dataclass

import numpy as np
import pytest

from tools.pipeline_eval.variants import v5_stream_recovery as stream


@dataclass
class Catalogue:
    names: tuple
    satellite_numbers: tuple
    satellites: tuple

    def __len__(self):
        return len(self.satellites)


def fixture(count):
    items = tuple(range(count))
    return Catalogue(tuple(map(str, items)), items, items)


def ecef(catalogue, origin, time):
    ids = np.array(catalogue.satellites)
    p = np.broadcast_to(
        ids[:, None, None] + 17.25 * time[None, :, None] + origin, (len(ids), len(time), 3)
    )
    return p, -p / 18, ids % 5 != 4


def test_eligible_state_store_preserves_source_order_and_exact_values(tmp_path):
    cat = fixture(stream.BLOCK + 9)
    knots = np.arange(-40.0, 341.0)
    reference_p, reference_v, mask = ecef(cat, 100, knots)
    reports = []
    with ExitStack() as stack:
        pos, vel, valid = stream.stream_states(ecef, stack, tmp_path, reports, cat, 100, knots)
        np.testing.assert_array_equal(valid, mask)
        p, v = pos[valid], vel[valid]
        np.testing.assert_array_equal(p[:], reference_p[mask])
        np.testing.assert_array_equal(v[-1], reference_v[mask][-1])
        assert p.shape == reference_p[mask].shape and p.finite
        assert not p[0].flags.writeable
        assert reports[0]["scratch_bytes"] == p.nbytes + v.nbytes
        with pytest.raises(ValueError, match="usable mask"):
            pos[mask.copy()]


def test_projection_uses_full_order_with_a_single_bounded_read_at_a_time(tmp_path):
    count = 2 * stream.BLOCK + 8
    cat = fixture(count)
    knots = np.arange(12.0)
    time = np.arange(6)
    positions = [(3, 6), (11, 13)]
    widths = []

    def project(bank, points, sites, *, phase_seconds):
        p, v = bank["position_km"][:, points, 0], bank["velocity_km_s"][:, points, 0]
        widths.append(len(p))
        return [(p * lat + v * lon + phase_seconds, v - p) for lat, lon in sites]

    with ExitStack() as stack:
        pos, vel, valid = stream.stream_states(ecef, stack, tmp_path, [], cat, 100, knots)
        bank = dict(time_s=knots, position_km=pos[valid], velocity_km_s=vel[valid])
        pa, va, ok = ecef(cat, 100, knots)
        events = dict(projected_grids=0, max_output_grid_bytes=0, max_state_read_bytes=0)
        candidate = stream.project_rows(project, events, bank, time, positions, phase_seconds=0.2)
        assert widths == [stream.BLOCK, int(ok.sum()) - stream.BLOCK]
        reference = project(
            dict(position_km=pa[ok], velocity_km_s=va[ok]), time, positions, phase_seconds=0.2
        )
        np.testing.assert_array_equal(candidate, reference)
        assert events["max_state_read_bytes"] == 2 * stream.BLOCK * 3 * 8 * len(knots)
        with pytest.raises(ValueError, match="bounded row block"):
            pos[valid][: stream.BLOCK + 1]


def test_audit_keeps_errors_and_nonfinite_raw_values_across_blocks(tmp_path):
    cat = fixture(stream.BLOCK + 6)
    time = np.arange(12.0)

    class Array:
        def __init__(self, sats):
            self.ids = sats

        def sgp4(self, jd, fr):
            sats = np.asarray(self.ids)
            error = np.repeat(sats[:, None] % 6, len(jd), axis=1).astype(np.uint8)
            p = np.repeat((sats[:, None] + jd)[..., None], 3, axis=2)
            p[error == 5] = np.nan
            return error, p, -p

    expected = Array(cat.satellites).sgp4(time, time)
    with ExitStack() as stack:
        adapter = stream.stream_audit(Array, stack, tmp_path, [], cat.satellites)
        error, pos, vel = adapter.sgp4(time, time)
        np.testing.assert_array_equal(error, expected[0])
        np.testing.assert_array_equal(pos[stream.BLOCK :], expected[1][stream.BLOCK :])
        np.testing.assert_array_equal(vel[5], expected[2][5])
        assert not pos.finite
