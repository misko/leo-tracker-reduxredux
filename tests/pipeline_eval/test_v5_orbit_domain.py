from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.localization_v3 import discovery
from leo.analysis.localization_v3 import scan as kernel
from leo.analysis.localization_v3.region import SearchRegion
from leo.operations import localization_v3_inputs
from leo.sky.frames import (
    greenwich_mean_sidereal_time_rad,
    julian_day_from_utc_ns,
    teme_to_ecef,
)
from leo.sky.propagation import parse_element_sets, propagate_grid
from leo.sky.sampling import SamplingGrid
from tools.pipeline_eval.variants import orbit_projector
from tools.pipeline_eval.variants import v5_orbit_domain as domain
from tools.pipeline_eval.variants.algo08_sparse_rank_projection import (
    ProjectedRows,
    sparse_rank_projection,
)

TLE = (
    "0 VANGUARD 1\n"
    "1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753\n"
    "2 00005  34.2682 331.5174 1849677 331.7664  19.3264 10.82419157413661\n"
)


def ecef_states(catalogue, origin, times):
    utc = origin + np.rint(times * 1e9).astype(np.int64)
    state = propagate_grid(catalogue, SamplingGrid(tuple(map(int, utc)), 0, 1.0))
    jd, fraction = julian_day_from_utc_ns(utc)
    p, v = teme_to_ecef(state.position_teme_km, state.velocity_teme_km_s,
                       greenwich_mean_sidereal_time_rad(jd, fraction))
    return p, v, state.usable


def test_both_edges_reuse_original_states_and_sgp4_geometry(tmp_path):
    catalogue = parse_element_sets(TLE)
    origin = catalogue.element_epoch_utc_ns()[0] + 300_000_000_000
    nominal = np.arange(-17.0, 318.0)
    times = np.array([0.0, 150.0, 300.0])
    knots = domain.support_knots(nominal, times, [-18, 18], derivative_step_s=0.05)
    np.testing.assert_array_equal(knots, [-19, -18, 318, 319])
    p, v, usable = ecef_states(catalogue, origin, nominal)
    ep, ev, extra_usable = ecef_states(catalogue, origin, knots)
    assert usable.all() and extra_usable.all()
    bank = dict(time_s=nominal, position_km=p, velocity_km_s=v)
    extended = domain.splice_bank(bank, knots, ep, ev)
    np.testing.assert_array_equal(extended["position_km"][:, 2:-2], p)
    np.testing.assert_array_equal(extended["velocity_km_s"][:, 2:-2], v)
    exact_knots = np.arange(-19.0, 320.0)
    truth_p, truth_v, good = ecef_states(catalogue, origin, exact_knots)
    assert good.all()
    independently_propagated = dict(time_s=exact_knots, position_km=truth_p, velocity_km_s=truth_v)
    np.testing.assert_array_equal(extended["position_km"], truth_p)
    np.testing.assert_array_equal(extended["velocity_km_s"], truth_v)
    lib = tmp_path / "project.so"
    orbit_projector.compile_kernel(lib)
    fitter = orbit_projector.Projector(lib)
    for phase, control in [(-18.0, independently_propagated), (18.0, independently_propagated),
                           (0.0, bank), (15.0, bank)]:
        a = fitter.evaluate(orbit_projector.prepare(extended, times, phase), 37, -122)
        b = fitter.evaluate(orbit_projector.prepare(control, times, phase), 37, -122)
        for observed, expected in zip(a, b, strict=True):
            np.testing.assert_array_equal(observed, expected)


@pytest.mark.parametrize(
    "times,phase,step",
    [([-0.001, 300], [18], 0.05), ([0, 300.0001], [18], 0.05), ([0, 300], [31], 0.05),
     ([0, 300], [float("nan")], 0.05), ([0, 300], [18], 0.25)],
)
def test_invalid_observation_phase_or_derivative_domain_is_rejected(times, phase, step):
    with pytest.raises(ValueError, match="outside the admissible causal support domain"):
        domain.support_knots(np.arange(-17.0, 318.0), times, phase, derivative_step_s=step)


def test_only_required_extra_lattice_knots_are_created():
    bank = np.arange(-17.0, 318.0)
    times = [0.01, 299.9648356]
    np.testing.assert_array_equal(domain.support_knots(bank, times, [-16.97800811383089],
                                                       derivative_step_s=0.05), [-18])
    assert not len(domain.support_knots(bank, times, [15.0], derivative_step_s=0.05))


def test_short_sgp4_requests_use_two_local_original_seam_knots():
    bank = np.arange(-17.0, 318.0)
    np.testing.assert_array_equal(domain.propagation_times(bank, np.array([-18])), [-18, -17, -16])
    np.testing.assert_array_equal(domain.propagation_times(bank, np.array([318])), [316, 317, 318])
    np.testing.assert_array_equal(
        domain.propagation_times(bank, np.array([318, 319])), [317, 318, 319]
    )


@pytest.mark.parametrize("sparse", [False, True])
def test_corner_support_wraps_the_active_projection(monkeypatch, tmp_path, sparse):
    catalogue = parse_element_sets(TLE)
    origin = catalogue.element_epoch_utc_ns()[0] + 300_000_000_000
    nominal = np.arange(-17.0, 318.0)
    times = np.array([0.0, 150.0, 300.0])
    p, v, usable = ecef_states(catalogue, origin, nominal)
    assert usable.all()
    norad = np.array(catalogue.satellite_numbers)
    bank = dict(time_s=nominal, position_km=p, velocity_km_s=v, norad=norad)

    lib = tmp_path / "project.so"
    orbit_projector.compile_kernel(lib)
    projector = orbit_projector.Projector(lib)
    monkeypatch.setattr(kernel, "prepare_phase_geometry", orbit_projector.prepare)
    monkeypatch.setattr(kernel, "phase_linear_frequency", projector.evaluate)
    monkeypatch.setattr(localization_v3_inputs, "regional_bank",
                        lambda *_: dict(catalogue=catalogue, bank=bank))
    scan = object.__new__(kernel.ScanLikelihood)
    scan.times, scan.sky, scan.norads = times, bank, norad
    scan.origin_utc_ns = origin
    scan.center, scan.scale = (37.0, -122.0), 89.0
    scan.search_region = SearchRegion(scan.center, width_km=25.0)
    radius = scan.search_region.half_width_km
    corner = (radius, -radius)
    columns = np.array([0, 2])

    def project(current, state, anchor, _method):
        base = projector.evaluate(orbit_projector.prepare(bank, times), *current.latlon(anchor))
        return current.shifted(base, state, anchor)

    monkeypatch.setattr(discovery, "explore", project)
    digest = sha256(Path(kernel.__file__).read_bytes()).hexdigest()
    projection = (sparse_rank_projection(scan, expected_source_sha256=digest)
                  if sparse else nullcontext())

    with domain.corner_support() as work:
        localization_v3_inputs.regional_bank(catalogue, origin)
        with projection as counts:
            shifted = scan.shifted
            for phase, extra_knot in [(-17.0, -18.0), (17.0, 318.0)]:
                phases = np.array([phase])
                with pytest.raises(ValueError, match=domain.OUTSIDE):
                    discovery.explore(scan, phases, (0.0, 0.0), "receiver_smooth")
                actual = discovery.explore(scan, phases, corner, "receiver_smooth")

                extended = np.sort(np.r_[nominal, extra_knot])
                expected_p, expected_v, usable = ecef_states(catalogue, origin, extended)
                assert usable.all()
                expected_bank = dict(
                    time_s=extended, position_km=expected_p, velocity_km_s=expected_v,
                )
                expected = projector.evaluate(
                    orbit_projector.prepare(expected_bank, times, phases), *scan.latlon(corner),
                )
                for observed, target in zip(actual, expected, strict=True):
                    assert isinstance(observed, ProjectedRows if sparse else np.ndarray)
                    np.testing.assert_array_equal(observed[:, columns], target[:, columns])
                assert scan.shifted == shifted
            if sparse:
                assert counts["column_requests"] == 6
                assert counts["materialized_bytes"] == 0

    assert work["corner_projections_extended"] == work["sgp4_calls"] == 2
    assert work["new_state_count"] == 2
    assert work["added_knots_s"] == [-18.0, 318.0]
    assert "shifted" not in vars(scan)
