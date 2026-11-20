from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import v5_nomination_memory as bounded


def geometry(bank, times, lat, lon, *, phase_seconds):
    identity = bank["position_km"][:, 0, 0]
    track = identity[:, None] + phase_seconds[:, None] * times[None, :]
    return track, np.broadcast_to(identity[:, None] % 3 - 1, track.shape)


def score(values, radio, frequency, derivative, row_widths, covariance, groups):
    corrected = frequency - values[None, :] + radio[None, :]
    aliases = np.rint(corrected[:, :2])
    phase_z = (derivative.sum(axis=1) - row_widths) / covariance[0, 0]
    return dict(score=(corrected**2).sum(axis=1), phase_z=phase_z, aliases=aliases)


def test_tiled_scoring_covers_all_satellites_and_preserves_dense_rf_rank():
    count = 2 * bounded.TILE + 3
    rows = np.arange(count, dtype=float)
    times = np.arange(6, dtype=float) / 4
    sky = dict(time_s=times, position_km=rows[:, None, None], velocity_km_s=rows[:, None, None])
    phases, widths = rows / 10, rows + 1
    data = dict(
        times=times,
        values=times * 2,
        q=times + 1,
        radio=times[:, None],
        coefficient=np.array([3.0]),
        radio_width=1,
        base_covariance=np.diag(times + 1),
        groups=np.array([0, 0, 0, 1, 1, 1]),
    )
    dense, elevation = geometry(sky, times, 0, 0, phase_seconds=phases)
    plus, _ = geometry(sky, times, 0, 0, phase_seconds=phases + 0.01)
    minus, _ = geometry(sky, times, 0, 0, phase_seconds=phases - 0.01)
    expected = score(
        data["values"],
        times * 3,
        dense * data["q"],
        (plus - minus) / 0.02 * data["q"],
        widths,
        data["base_covariance"],
        data["groups"],
    )
    calls = []

    def project(*args, **kwargs):
        calls.append(len(args[0]["position_km"]))
        return geometry(*args, **kwargs)

    observations = []

    def observe(*args):
        observations.append(args)

    result, aliases = bounded.screen(
        SimpleNamespace(phase_frequency_grid=project, coarse_phase_scores=score),
        sky,
        (0, 0),
        phases,
        widths,
        data,
        observe,
    )
    assert calls == [bounded.TILE] * 6 + [3] * 3
    reference = np.where(elevation.min(axis=1) >= 0, expected["score"], np.inf)
    np.testing.assert_array_equal(result, reference)
    np.testing.assert_array_equal(np.argsort(result), np.argsort(reference))
    np.testing.assert_array_equal(aliases, expected["aliases"])
    observed, minimum, payload = observations[0]
    np.testing.assert_array_equal(minimum, elevation.min(axis=1))
    np.testing.assert_array_equal(observed["phase_z"], expected["phase_z"])
    assert payload == 4 * bounded.TILE * len(times) * times.itemsize
