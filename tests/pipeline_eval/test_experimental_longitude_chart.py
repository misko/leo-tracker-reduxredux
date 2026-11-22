from hashlib import sha256
from math import remainder
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.localization_v3 import discovery
from leo.analysis.localization_v3 import scan as kernel
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.contracts.algo08_region import Algo08Region
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from leo.sky.propagation import ElementSetCatalogue
from tests.operations.test_causal_tle_catalogue import at_day
from tools.pipeline_eval.variants import orbit_projector, v5_core
from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery
from tools.pipeline_eval.variants.algo08_sparse_rank_projection import sparse_rank_projection
from tools.pipeline_eval.variants.experimental import regional_reassignment
from tools.pipeline_eval.variants.experimental.longitude_chart import longitude_chart
from tools.pipeline_eval.variants.experimental.regional_bound_guard import inspect_boundary
from tools.pipeline_eval.variants.v5_direct_cavity import numerical_bindings


@pytest.fixture(scope="module")
def projector(tmp_path_factory):
    library = tmp_path_factory.mktemp("longitude-projector") / "projector.so"
    orbit_projector.compile_kernel(library)
    return orbit_projector.Projector(library)


def seam_offer(sign):
    return Algo08Region((2.0, sign * 179.88764265806918), 25.0, (2.0, -sign * 179.85))


def coast(site, knots):
    origin = geodetic_to_ecef_km(*site, 0)
    east, north, up = ecef_to_enu_matrix(*site)
    velocity = 7 * east + 2 * north
    position = origin + 550 * up + 80 * north + (knots[:, None] - 8) * velocity
    return position[None, :], np.broadcast_to(velocity, (1, len(knots), 3)).copy()


def bank_at(site, knots):
    position, velocity = coast(site, knots)
    return dict(
        time_s=knots,
        position_km=position,
        velocity_km_s=velocity,
        norad=np.array([17]),
        phase_sigma_s=np.ones(1),
    )


def synthetic_scan(offer, anchor):
    region = SearchRegion(offer.center, offer.width_km)
    site = region.latlon(anchor)
    bank = bank_at(site, np.arange(-19.0, 319.0))
    times = np.arange(61.0)
    values, _, _ = phase_linear_frequency(prepare_phase_geometry(bank, times, 0.75), *site)
    track = dict(
        key="synthetic",
        receiver=1,
        channel=1,
        rf_hz=11.5e9,
        times=times,
        values=values[0],
        observation_ids=list(range(len(times))),
    )
    previous = at_day(232.0)  # No previous elements for the synthetic NORAD 17.
    return kernel.ScanLikelihood(
        [track],
        bank,
        {},
        origin_utc_ns=0,
        regional_center=offer.screen_center,
        noise=dict(
            constant_radio_sigma_hz=150.0,
            per_observation_noise_sigma_hz={},
            extra_parameter_BIC_gain=0,
        ),
        search_region=region,
        previous_tle=previous,
        previous_tle_sha256=sha256(previous.encode()).hexdigest(),
    )


@pytest.mark.parametrize("sign", [-1, 1])
def test_discovery_projects_shifted_candidates_on_both_sides_of_the_seam(sign, projector):
    offer = seam_offer(sign)
    anchor = (sign * 12.5, 12.5)
    digest = sha256(Path(kernel.__file__).read_bytes()).hexdigest()
    with numerical_bindings(projector):
        scan = synthetic_scan(offer, anchor)
        region = scan.search_region
        site = region.latlon(anchor)
        assert abs(site[1]) < 180.0
        old_east = region.native_point(scan, anchor)[0]
        assert abs(old_east) > 39000
        with (
            dense_discovery(scan, reuse_associations=True) as associations,
            sparse_rank_projection(scan, expected_source_sha256=digest) as sparse,
            longitude_chart(),
        ):
            native = region.native_point(scan, anchor)
            assert -18 < sign * native[0] < -16
            shifted_site = scan.latlon(native)
            assert abs(shifted_site[1]) <= 180.0
            assert remainder(shifted_site[1] - site[1], 360.0) == pytest.approx(0, abs=1e-13)
            seed, trace = discovery.explore(
                scan, discovery.zero_state(scan), anchor, "receiver_smooth"
            )
            nodes = v5_core.ranked_initial_nodes(scan)
        assert region.native_point(scan, anchor)[0] == old_east
    assert associations["association_reused"] > 0
    assert sparse["calls"] >= sparse["active_rows"] > 0
    assert nodes[0]["seed"]["rows"][0]["candidate_norad"] == 17
    assert trace["hypotheses"]["17"]["phase_s"] == pytest.approx(0.75, abs=0.02)
    assert seed["rows"][0]["candidate_norad"] == 17
    assert seed["rows"][0]["rms_hz"] < 10


def test_normal_chart_keeps_coordinates_and_guard_probes_byte_exact():
    offer = Algo08Region((38.0, -122.0), 25.0, (37.5, -121.5))
    scan = synthetic_scan(offer, (0.0, 0.0))
    region = scan.search_region

    def coordinates():
        coordinates = []
        for anchor in region.grid:
            point = region.native_point(scan, anchor)
            coordinates.append((region.latlon(anchor), tuple(point), scan.latlon(point)))
        return np.asarray(coordinates).tobytes()

    old_coords = coordinates()
    old_probes = list(regional_reassignment.probes(region))
    with longitude_chart():
        assert coordinates() == old_coords
        assert list(regional_reassignment.probes(region)) == old_probes


@pytest.mark.parametrize("sign", [-1, 1])
def test_terminal_guard_scores_the_wrapped_exterior_around_a_legal_square(sign, monkeypatch):
    offer = seam_offer(sign)
    region = SearchRegion(offer.center, offer.width_km)
    target = (sign * 62.5, -5.0)
    latitude, unwrapped = region.latlon(target)
    assert abs(unwrapped) > 180
    site = (latitude, remainder(unwrapped, 360.0))
    times = np.arange(61.0)
    bank = bank_at(site, np.arange(-1.0, 62.0))
    observed, _, _ = phase_linear_frequency(prepare_phase_geometry(bank, times), *site)
    ids = [range(len(times)), range(len(times), 2 * len(times))]
    prepared = dict(
        observations=[
            dict(observation_id=i, receiver=receiver)
            for receiver, track_ids in enumerate(ids, 1)
            for i in track_ids
        ],
        tracks=[
            dict(
                key=str(receiver),
                receiver=receiver,
                observation_ids=list(track_ids),
                rf_hz=11.5e9,
                times=times,
                values=observed[0],
            )
            for receiver, track_ids in enumerate(ids, 1)
        ],
        metadata=dict(anchor_utc_ns=0),
    )
    catalogue = ElementSetCatalogue(("synthetic",), (17,), (object(),))

    def states(active, _origin, knots):
        assert active.satellite_numbers == (17,)
        return *coast(site, knots), np.ones(1, bool)

    monkeypatch.setattr(regional_reassignment, "ecef_states", states)
    endpoints = {arm: (sign * 12.5, 0.0) for arm in ("c0", "fitted_c")}

    def score():
        return regional_reassignment.evaluate_veto(prepared, catalogue, region)

    old = inspect_boundary(endpoints, offer.width_km, score, terminal_only=True)
    assert not old["evaluated"] and old["diagnostic_error"].endswith("geographic domain")
    with longitude_chart():
        wrapped = list(regional_reassignment.probes(region))
        result = inspect_boundary(endpoints, offer.width_km, score, terminal_only=True)
    assert len(wrapped) == 96
    assert all(-180 <= point["latlon"][1] <= 180 for point in wrapped)
    (exterior_site,) = (point for point in wrapped if tuple(point["xy_km"]) == target)
    assert exterior_site["side"] == "exterior" and exterior_site["latlon"] == site
    assert result["evaluated"] and result["complete"] and result["would_withhold"]
    assert result["probes_evaluated"] == 96
    assert result["catalogue_orbits"] == result["potentially_visible_orbits"] == 1
    for receiver in result["receivers"].values():
        assert tuple(receiver["exterior_xy_km"]) == target
        assert receiver["gain"] > 0
