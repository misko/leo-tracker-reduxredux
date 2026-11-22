import json
from hashlib import sha256
from math import remainder
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import discovery
from leo.analysis.localization_v3 import scan as kernel
from leo.analysis.localization_v3.region import SearchRegion
from leo.analysis.localization_v4 import backend
from leo.analysis.research.phase_linear_geometry import (
    phase_linear_frequency,
    prepare_phase_geometry,
)
from leo.contracts.algo08_region import Algo08Region
from leo.contracts.digests import canonical_digest
from leo.sky.frames import ecef_to_enu_matrix, geodetic_to_ecef_km
from leo.sky.propagation import ElementSetCatalogue
from leo.storage.fast_scan import FastScanStore
from tests.operations.test_causal_tle_catalogue import at_day
from tools import algo08_position, algo08_scan
from tools.pipeline_eval.qualification import experimental_publication
from tools.pipeline_eval.variants import orbit_projector, v5_core
from tools.pipeline_eval.variants.algo08_dense_discovery import dense_discovery
from tools.pipeline_eval.variants.algo08_sparse_rank_projection import sparse_rank_projection
from tools.pipeline_eval.variants.experimental import regional_bound_guard, regional_reassignment
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


def synthetic_guard(region, sign, monkeypatch):
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
    return target, site, prepared, catalogue


@pytest.mark.parametrize("sign", [-1, 1])
def test_terminal_guard_scores_the_wrapped_exterior_around_a_legal_square(sign, monkeypatch):
    offer = seam_offer(sign)
    region = SearchRegion(offer.center, offer.width_km)
    target, site, prepared, catalogue = synthetic_guard(region, sign, monkeypatch)
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


@pytest.fixture
def research_run(tmp_path, monkeypatch):
    assets = tmp_path / "release" / "assets"
    assets.mkdir(parents=True)
    config = assets / "tracks.json"
    config.write_text('{"config": {}}')
    detector = tmp_path / "receiver.so"
    detector.write_bytes(b"fixture detector")
    root = tmp_path / "output"
    root.mkdir()
    args = SimpleNamespace(
        recording=tmp_path / "unused",
        bulk_root=root,
        archive=tmp_path / "unused-tle",
        region=tmp_path / "offer.json",
    )
    checkout = Path(experimental_publication.__file__).resolve().parents[3]
    sources = {
        str(source): sha256((checkout / source).read_bytes()).hexdigest()
        for source in (
            experimental_publication.LONGITUDE_CHART_SOURCE,
            *experimental_publication.TERMINAL_VETO_SOURCES,
        )
    }
    spec = dict(
        solver="stock",
        detector=str(detector),
        sources=sources,
        detector_sha256=sha256(detector.read_bytes()).hexdigest(),
    )
    monkeypatch.setattr(experimental_publication, "RELEASE", assets.parent)
    monkeypatch.setattr(
        algo08_scan,
        "PINS",
        {
            "tracks.json": sha256(config.read_bytes()).hexdigest(),
            "cancellation-factors.so": "fixture",
        },
    )
    return args, spec


@pytest.mark.parametrize("sign", [-1, 1])
@pytest.mark.parametrize("center", [179.6, 179.8, 179.88764265806918])
def test_research_solver_wraps_ranking_and_guard_during_the_same_solve(
    research_run,
    monkeypatch,
    projector,
    sign,
    center,
):
    args, spec = research_run
    offer = Algo08Region((2.0, sign * center), 25.0, (2.0, -sign * 179.85))
    args.region.write_text(json.dumps(offer.document()))
    region = SearchRegion(offer.center, offer.width_km)
    target, _, prepared, catalogue = synthetic_guard(region, sign, monkeypatch)
    ready = dict(status="inputs_prepared", tracks=prepared)
    orig_chart = (SearchRegion.latlon, SearchRegion.native_point, kernel.ScanLikelihood.latlon)
    orig_solvers = (algo08_position.solve, algo08_scan.solve)
    evaluations = []

    def chart():
        return SearchRegion.latlon, SearchRegion.native_point, kernel.ScanLikelihood.latlon

    def infer(ready, search_region, _bound, _stages, *, selected_evidence):
        assert chart() != orig_chart and search_region == region
        scan = synthetic_scan(offer, (sign * 12.5, 12.5))
        ranked = v5_core.ranked_initial_nodes(scan)
        assert ranked[0]["seed"]["rows"][0]["candidate_norad"] == 17
        endpoint = {"endpoint_east_north_km": (sign * 12.5, 0.0)}
        selected_evidence(ready, {"arms": dict.fromkeys(("c0", "fitted_c"), endpoint)}, None)
        return dict(status="ok", arms={}, metrics={})

    def score(tracks, _archive, search_region, *, terminal_only):
        assert chart() != orig_chart and terminal_only and tracks is prepared
        result = regional_reassignment.evaluate_veto(tracks, catalogue, search_region)
        evaluations.append(result)
        return result

    inventory = dict(recording_name=args.recording.name, window_count=1)
    inventory_sha = canonical_digest(inventory)
    session = "fast-" + inventory_sha[7:39]
    raw = canonical_digest([inventory_sha, [canonical_digest("synthetic window")]])
    measurements = [dict(channel=1, receiver_id=rx, candidates=[]) for rx in (0, 1)]

    def acquire(selected_session, selected_inventory, _inventory, _assets):
        assert chart() == orig_chart
        assert (selected_session, selected_inventory) == (session, inventory_sha)
        return dict(
            source=dict(
                probes=measurements,
                session_id=session,
                input_manifest_sha256=inventory_sha,
                raw_recording_authority_digest=raw,
                analysis_manifest_sha256=canonical_digest(
                    [
                        "cancellation",
                        raw,
                        spec["detector_sha256"],
                        measurements,
                    ]
                ),
            ),
            provenance=dict(
                rf_mapping_authorities=[], processed_windows=1, window_count=1, invalid_capture=0
            ),
        )

    monkeypatch.setattr(
        FastScanStore,
        "inventory",
        lambda *_a, **_kw: (session, inventory_sha, inventory),
    )
    monkeypatch.setattr(backend, "read_manifest", lambda _path: {})
    monkeypatch.setattr(backend, "validate_manifest", lambda *_a, **_kw: {"binary": None})
    monkeypatch.setattr(algo08_position, "NativeBound", lambda _binary: None)
    monkeypatch.setattr(orbit_projector, "Projector", lambda _path: projector)
    monkeypatch.setattr(algo08_position, "prepare_native_scan", lambda *_a, **_kw: ready)
    monkeypatch.setattr(algo08_position, "_prepared_values", lambda value: value)
    monkeypatch.setattr(algo08_scan, "acquire", acquire)
    monkeypatch.setattr(v5_core, "infer", infer)
    monkeypatch.setattr(regional_bound_guard, "causal_probes", score)
    receipt = experimental_publication.run(
        args,
        dict(
            spec,
            wrapped_longitude=True,
            regional_veto=True,
            regional_veto_terminal_only=True,
        ),
    )
    assert (algo08_position.solve, algo08_scan.solve) == orig_solvers and chart() == orig_chart
    assert receipt["decision"] == "withheld" and receipt["region"] == offer.document()
    workspace = FastScanStore(args.bulk_root).automatic_workspace(receipt["run_id"])
    terminal = json.loads((workspace / "terminal.json").read_bytes())
    assert canonical_digest(terminal) == receipt["terminal_sha256"]
    assert terminal["reason"] == "both_receivers_support_far_exterior"
    assert terminal["arms"] == dict.fromkeys(("c0", "fitted_c"), {"latlon": None})
    (guard,) = evaluations
    assert guard["complete"] and guard["probes_evaluated"] == 96
    assert all(tuple(row["exterior_xy_km"]) == target for row in guard["receivers"].values())


@pytest.mark.parametrize("flag", [None, False, True])
def test_research_chart_leaves_acquisition_unchanged_and_restores_after_failure(
    research_run,
    monkeypatch,
    flag,
):
    args, spec = research_run
    args.region.write_text(json.dumps(seam_offer(1).document()))
    if flag is not None:
        spec["wrapped_longitude"] = flag
    original = SearchRegion.native_point

    def solve():
        assert (SearchRegion.native_point is not original) == bool(flag)
        raise RuntimeError("synthetic solve failure")

    def analyze(*_args):
        assert SearchRegion.native_point is original
        algo08_position.solve()

    monkeypatch.setattr(algo08_position, "solve", solve)
    monkeypatch.setattr(algo08_scan, "analyze", analyze)
    with pytest.raises(RuntimeError, match="synthetic solve failure"):
        experimental_publication.run(args, spec)
    assert algo08_position.solve is solve and SearchRegion.native_point is original


@pytest.mark.parametrize("failure", ["type", "absent-pin", "wrong-pin", "outside-import"])
def test_research_chart_rejects_unbound_options_before_acquisition(
    research_run,
    monkeypatch,
    failure,
):
    args, spec = research_run
    source = str(experimental_publication.LONGITUDE_CHART_SOURCE)
    spec["wrapped_longitude"] = "true" if failure == "type" else True
    if failure == "absent-pin":
        del spec["sources"][source]
    if failure == "wrong-pin":
        spec["sources"][source] = "0" * 64
    if failure == "outside-import":
        monkeypatch.setattr(
            experimental_publication.util,
            "find_spec",
            lambda _: SimpleNamespace(
                origin=str(args.bulk_root / source),
            ),
        )
    with pytest.raises(ValueError, match="Boolean wrapped longitude|pinned chart source"):
        experimental_publication.run(args, spec)
