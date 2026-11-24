import json
from collections import Counter
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from reports.ALGO08.v3.full_mask_design import _select_full, borrowed_normal_design
from tests.operations.test_causal_tle_catalogue import at_day

BINARY = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c"
              "/assets/native/native_bound.so")


class ArraySubclass(np.ndarray):
    pass


def ordinary(features, scale, keep):
    result = features[keep]
    np.multiply(result, scale, out=result)
    return result


def test_full_view_preserves_signed_zero_and_subnormal():
    features = np.array([[-0., np.nextafter(0., 1.)], [0., -1.]])
    keep, scale = np.ones(2, dtype=bool), np.ones(2)
    counts = Counter()
    result = _select_full(features, scale, keep, ordinary, counts)
    assert np.shares_memory(result, features)
    assert features.flags.writeable and not result.flags.writeable
    assert result.tobytes() == ordinary(features, scale, keep).tobytes()
    assert counts["unit_multiplies_avoided"] == 4
    assert counts["design_copy_bytes_avoided"] == 32

    keep[0] = False
    assert _select_full(features, scale, keep, ordinary, counts).shape == (1, 2)
    keep[0] = True
    scale[1] = .3
    assert _select_full(features, scale, keep, ordinary, counts).tobytes() == (
        ordinary(features, scale, keep).tobytes()
    )
    assert counts["mask_fallbacks"] == counts["scale_fallbacks"] == 1


@pytest.mark.parametrize("layout", [
    lambda a: np.asfortranarray(a),
    lambda a: a[:, ::-1],
    lambda a: a.astype(np.float32),
    lambda a: a.view(ArraySubclass),
])
def test_unsupported_array_preserves_the_original_selector(layout):
    features = layout(np.array([[0., 1.], [2., 3.]]))
    keep, scale = np.ones(2, dtype=bool), np.ones(2)
    counts = Counter()
    result = _select_full(features, scale, keep, ordinary, counts)
    assert type(result) is type(ordinary(features, scale, keep))
    assert result.tobytes() == ordinary(features, scale, keep).tobytes()
    assert counts == {"shape_fallbacks": 1}


def synthetic_scan(site, owner, *, shared_groups=True):
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.scan import ScanLikelihood
    from leo.analysis.research.phase_linear_geometry import (
        phase_linear_frequency,
        prepare_phase_geometry,
    )
    from leo.analysis.research.retained_track_likelihood import PERIOD
    from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km

    region = SearchRegion(site)
    east, north, up = ecef_to_enu_matrix(*site)
    observer = geodetic_to_ecef_km(*site, 0)
    knots = np.arange(-25., 326.)
    velocity = np.array([
        7.2 * east, 7.3 * north, 4.8 * (east + north), 4.7 * (east - north),
    ])
    positions = (
        observer + np.array([490., 520., 480., 510.])[:, None] * up
        + np.array([80. * north, -70. * east, 120. * east - 25. * north, 90. * north])
    )
    positions = positions[:, None] + (knots[None, :, None] - 53.) * velocity[:, None]
    bank = {
        "time_s": knots,
        "position_km": positions,
        "velocity_km_s": np.broadcast_to(velocity[:, None], positions.shape),
        "norad": np.array([99991, 99992, 99993, 99994]),
        "phase_sigma_s": np.ones(4),
    }
    tracks = []
    aliases = [0, -1, 0, 1]
    radios = [(1, 1, 10.94e9), (2, 8, 12.69e9)]
    radios += ([(1, 2, 11.17e9), (2, 7, 12.27e9)] if shared_groups
               else [(1, 7, 12.27e9), (2, 2, 11.17e9)])
    for i, (radio, channel, rf) in enumerate(radios):
        times = np.arange(43) + 10.
        geometry = prepare_phase_geometry(bank, times, (0.15, -0.5, 0.23, -0.27))
        frequency, _, _ = phase_linear_frequency(geometry, *region.latlon([3.2, -4.1]))
        values = (
            frequency[i] * rf / 11.5e9 - aliases[i] * PERIOD
            + 120. * (rf / 1e9 - 11.5) + 35. * np.sin(times)
        )
        tracks.append(dict(key=f"track-{i}", receiver=radio, channel=channel, rf_hz=rf,
                           times=times, values=values,
                           observation_ids=[f"synthetic-{i}-{j}" for j in range(len(times))]))
    previous = at_day(232)
    scan = ScanLikelihood(
        tracks, bank, {}, origin_utc_ns=0, regional_center=site,
        noise=dict(constant_radio_sigma_hz=150., extra_parameter_BIC_gain=0,
                   per_observation_noise_sigma_hz={}),
        search_region=region, previous_tle=previous,
        previous_tle_sha256=sha256(previous.encode()).hexdigest(), bound=owner,
    )
    assert scan.curved == [0, 1, 2, 3]
    rows = [
        dict(component=track["key"], active_curvature=True, candidate_index=i,
             candidate_norad=int(bank["norad"][i]))
        for i, track in enumerate(tracks)
    ]
    state = dict(beta=np.zeros(8), phases=np.zeros(4), extra={},
                 smooth=np.zeros((2, scan.rx_basis[0].shape[1])))
    return scan, dict(seed=dict(rows=rows, state=state), aliases=aliases)


def byte_identity(value):
    if isinstance(value, dict):
        return {key: byte_identity(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return tuple(map(byte_identity, value))
    array = np.asarray(value)
    assert not array.dtype.hasobject
    return array.dtype.str, array.shape, array.tobytes()


def score(site, arm, borrowed):
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools.pipeline_eval.variants.algo08_curved_design import measured_curved_design

    with measured_curved_design(enabled=True) as original_counts:
        owner = NativeBound(BINARY)
        scan, node = synthetic_scan(site, owner)
        scope = borrowed_normal_design(owner) if borrowed else nullcontext(Counter())
        with scope as counts:
            calculate = position.NormalPosition.calculate
            trajectory = []

            def record(self, x):
                result = calculate(self, x)
                trajectory.append(byte_identity((x, result)))
                return result

            with patch.object(position.NormalPosition, "calculate", record):
                problem, result, history = position.refreshed(
                    scan, 150., node, arm, rounds=2, iterations=3,
                )
                for point in ((0., 0.), (1.25, -2.0), (-12.5, 12.5)):
                    problem.calculate(np.array(point))
            fields = (
                result, history, problem.scan.search_region.latlon(result["parameters"]),
                problem.members, problem.alias, problem.values, problem.keep, trajectory,
            )
        assert owner.counts["activated"] == len(trajectory), owner.counts
        native_counts = dict(owner.counts)
        owner.clear()
    return byte_identity(fields), original_counts, counts, native_counts, problem.hardware.shape


@pytest.mark.hardware
@pytest.mark.parametrize("site", [(0., 0.), (-23., 137.)])
@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_original_finalist_coordinates_and_full_scores_are_bit_exact(site, arm):
    baseline, original, _, native, shape = score(site, arm, borrowed=False)
    candidate, observed, work, trial_native, trial_shape = score(site, arm, borrowed=True)
    assert candidate == baseline
    assert shape == trial_shape and shape == (172, 8 + (arm == "fitted_c"))
    assert trial_native == native
    assert native["calls"] == original["normal_selection_direct"] == work["forwarded_calls"]
    assert observed["normal_selection_calls"] == original["normal_selection_calls"]
    assert observed["normal_selection_direct"] == original["normal_selection_direct"]
    assert original["direct_assembly_calls"] == observed["direct_assembly_calls"]
    assert work["unit_multiplies_avoided"] * 8 == work["design_copy_bytes_avoided"]
    assert work["mask_entries_checked"] == shape[0] * work["forwarded_calls"]
    print(json.dumps(dict(site=site, arm=arm, counts=work, native=native), sort_keys=True))


@pytest.mark.hardware
def test_live_partial_keep_changed_callback_and_original_native_fallback():
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools.pipeline_eval.variants.algo08_curved_design import measured_curved_design

    owner = NativeBound(BINARY, min_rcond=1.)
    with borrowed_normal_design(owner) as inactive:
        assert inactive == {"inactive_binding": 1}
    with measured_curved_design(enabled=True):
        scan, node = synthetic_scan((0., 0.), owner)
        full = position.NormalPosition(scan, node, 150., True)
        keep = full.keep.copy()
        keep[::3] = False
        partial = position.NormalPosition(scan, node, 150., True, keep=keep)
        x = np.zeros(2)
        ordinary_full = byte_identity(full.calculate(x))
        ordinary_partial = byte_identity(partial.calculate(x))
        assert owner.counts["fallback_ill_conditioned"] == 2, owner.counts

        with borrowed_normal_design(owner) as work:
            assert byte_identity(full.calculate(x)) == ordinary_full
            assert byte_identity(partial.calculate(x)) == ordinary_partial
            run = owner.run
            with patch.object(owner, "run", lambda *args: run(*args)):
                assert byte_identity(full.calculate(x)) == ordinary_full
        assert work["forwarded_calls"] == work["mask_fallbacks"] == work["owner_fallbacks"] == 1
        assert owner.counts["fallback_ill_conditioned"] == 5
    owner.clear()


@pytest.mark.hardware
def test_unsupported_private_native_layout_keeps_python_result():
    from leo.analysis.localization_v3 import position
    from leo.analysis.localization_v4.native_bound import NativeBound
    from tools.pipeline_eval.variants.algo08_curved_design import measured_curved_design

    owner = NativeBound(BINARY)
    with measured_curved_design(enabled=True):
        scan, node = synthetic_scan((-23., 137.), owner, shared_groups=False)
        problem = position.NormalPosition(scan, node, 150., False)
        point = np.array([1.25, -2.])
        original = byte_identity(problem.calculate(point))
        with borrowed_normal_design(owner) as work:
            assert byte_identity(problem.calculate(point)) == original
        assert work["forwarded_calls"] == 1
        assert owner.counts["fallback_unsupported"] == 2
        assert owner.counts["activated"] == 0
    owner.clear()
