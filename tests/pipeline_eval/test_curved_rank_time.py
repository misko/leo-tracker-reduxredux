from collections import defaultdict
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import runpy
import sys

import numpy as np
import pytest


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))

from curved_rank_time import compact_view, narrow_rank, projected_ranking, time_union
from empty_bootstrap import RELEASE, checked
from nomination_handoff import same
from polar_projection_trial import CAPSULE, CAPSULE_SHA, OFFER, OFFER_SHA, PROJECTOR_SHA


def audit():
    return defaultdict(int, admitted_epoch_counts=[])


def test_time_union_keeps_validation_edges_and_all_curved_repeats():
    times = np.array([0., 1., 2., 3., 4., 5., 6., 7., 8.])
    tracks = [np.array([2, 2, 4, 6]), np.array([4, 5, 5]), np.array([1, 3, 7])]
    assert time_union(times, tracks, [0, 1]).tolist() == [0, 2, 4, 5, 6, 8]
    assert not len(time_union(times, tracks, []))


@pytest.fixture
def scene():
    from leo.analysis.localization_v3 import scan as kernel
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v3.tracks import active_curvature
    from leo.sky.propagation import element_line_checksum
    from tools.pipeline_eval.variants import orbit_projector, v5_direct_cavity

    with np.load(BytesIO(checked(CAPSULE, CAPSULE_SHA)), allow_pickle=False) as saved:
        record = json.loads(saved["document"].item())
        bank = {k: saved[k] for k in ("time_s", "position_km", "velocity_km_s")}
    offer = json.loads(checked(OFFER, OFFER_SHA))["receipt"]["region"]
    choose = next(row for row in record["layouts"]["changed_only"]["rows"]
                  if active_curvature({k: np.asarray(row[k]) for k in ("times", "values")}))
    t = np.asarray(choose["times"])
    # Linear-only times are test inputs that exercise an interior gap and both
    # full range endpoints around one actual measured curved track.
    interior = (t[1:]+t[:-1])/2
    extra = np.unique(np.r_[t.min()-1., interior, t.max()+1.])
    rows = [dict(key=key, times=times, values=values, receiver=receiver, channel=channel,
                 rf_hz=rf, observation_ids=[f"{key}:{i}" for i in range(len(times))])
            for key, times, values, receiver, channel, rf in (
                ("measured", t, choose["values"], 1, 1, 11.5e9*choose["rf_ratio"]),
                ("linear", extra, extra*10, 2, 8, 11.75e9))]
    banks = len(bank["position_km"])
    bank.update(norad=np.asarray(record["norads"]), phase_sigma_s=np.full(banks, 4.))
    noise = dict(constant_radio_sigma_hz=150., per_observation_noise_sigma_hz={}, extra_parameter_BIC_gain=0.)
    library = RELEASE/"assets/projector.so"
    checked(library, PROJECTOR_SHA)
    # A valid fixture catalogue with no matching earlier element exercises the
    # normal absent-history branch without rereading any backing orbit archive.
    earlier = ("1 25544U 98067A   23073.02771182  .00017654  00000-0  32060-3 0  999",
               "2 25544  51.6427 244.1570 0006419  42.2167  74.9388 15.4995423538707")
    assert 25544 not in bank["norad"]
    prior = "\n".join(f"{line}{element_line_checksum(line)}" for line in earlier) + "\n"
    region = SearchRegion(offer["center"], offer["width_km"])
    with v5_direct_cavity.numerical_bindings(orbit_projector.Projector(library)):
        scan = kernel.ScanLikelihood(rows, bank, {}, origin_utc_ns=0, regional_center=offer["screen_center"],
                                     noise=noise, search_region=region, previous_tle=prior,
                                     previous_tle_sha256=sha256(prior.encode()).hexdigest())
        assert scan.curved == [0]
        yield scan, kernel, orbit_projector


@pytest.mark.frozen_v5_numerics
def test_shifted_and_nominal_planes_have_identical_exact_columns(scene):
    from leo.analysis.localization_v3 import discovery

    scan, kernel, projector = scene
    counts = audit()
    old, minimum, maximum = scan.times, scan.times[0], scan.times[-1]
    offsets = [(0., 0.), (-scan.search_region.half_width_km, scan.search_region.half_width_km)]
    phases = np.linspace(-.975, .475, len(scan.norads))

    def evaluate(current):
        result = []
        for xy in offsets:
            base = discovery.phase_linear_frequency(current.geometry, *current.search_region.latlon(xy))
            shifted = current.shifted(base, phases, current.search_region.native_point(current, xy))
            for planes in (base, shifted):
                result.extend(a[:, current.index[0]] for a in planes)
        return result

    plain = evaluate(scan)
    view = compact_view(scan, kernel, projector.Stencil, counts)
    assert minimum == view["times"][0] and maximum == view["times"][-1]
    assert len(view["times"]) < len(old)
    assert np.array_equal(view["times"][view["index"][0]], scan.tracks[0]["times"])
    compact = narrow_rank(evaluate, kernel, projector.Stencil, audit())(scan)
    assert all(a.tobytes() == b.tobytes() for a, b in zip(plain, compact, strict=True))
    assert scan.times is old

    def outside(current):
        base = discovery.phase_linear_frequency(current.geometry, *current.search_region.center)
        step = current.sky["time_s"][-1] - maximum
        return current.shifted(base, np.full(len(phases), step), current.search_region.native_point(current, (0., 0.)))

    for attempt in (outside, narrow_rank(outside, kernel, projector.Stencil, audit())):
        with pytest.raises(ValueError, match="never extrapolates"):
            attempt(scan)


@pytest.mark.frozen_v5_numerics
def test_regular_rank_entry_preserves_full_order_and_scores(scene):
    from catalogue_block_rank import install
    from leo.analysis.localization_v3 import discovery
    from proof_global_rank import rank_port
    from tools.pipeline_eval.variants import algo08_dense_discovery, algo08_sparse_rank_projection, v5_core
    import exact_named_route as entry

    scan, _, _ = scene
    times, geometry, indexes = scan.times, scan.geometry, scan.index
    share = runpy.run_path(str(entry.SHARING))["shared_rank_preparation"]
    counts = audit()

    def rank(counters, original):
        with (algo08_dense_discovery.dense_discovery(scan, reuse_associations=True),
              algo08_sparse_rank_projection.sparse_rank_projection(scan, expected_source_sha256=
                  "49f1f2e9d73b967f694e48033b6d02ea2e1d66285f7941c4f282f5b238e79f89")):
            return entry.rank_with_exact_inputs(original, share, install, discovery, [], counters)(scan)

    stock_work, candidate_work = defaultdict(int), defaultdict(int)
    original = rank_port(v5_core.ranked_initial_nodes)
    ordinary = rank(stock_work, original)
    with projected_ranking(counts):
        compact = rank(candidate_work, original)
    assert ordinary and same(ordinary, compact)
    assert candidate_work["calls"] == stock_work["calls"] > 0
    assert candidate_work == stock_work
    assert counts["compact_ranks"] == 1
    assert counts["admitted_epoch_counts"][0][0] > counts["admitted_epoch_counts"][0][1]
    assert scan.geometry is geometry and scan.times is times and scan.index is indexes


@pytest.mark.frozen_v5_numerics
def test_stock_full_index_fallback_and_restoration(scene):
    scan, kernel, projector = scene
    counts = audit()
    old_times, old_index = scan.times, scan.index
    calls = []

    from leo.analysis.localization_v3 import discovery

    def rank(current):
        calls.append(len(current.times))
        base = discovery.phase_linear_frequency(current.geometry, *current.search_region.center)
        point = current.search_region.native_point(current, (0., 0.))
        return current.association(discovery.zero_state(current), base, point, "shared_phase", all_tracks=True)

    ordinary = rank(scan)
    calls.clear()
    fallback = narrow_rank(rank, kernel, projector.Stencil, counts)(scan)
    assert same(fallback, ordinary) and len(fallback[1]) == 2
    assert calls[0] < calls[1] == len(old_times)
    assert counts["all_track_fallbacks"] == 1 and scan.times is old_times and scan.index is old_index

    scan.curved = [0, 1]
    assert compact_view(scan, kernel, projector.Stencil, counts) is None
    assert counts["full_union"] == 1
    scan.curved = [0]
    scan.sky["velocity_km_s"][0, 0] += 26
    assert compact_view(scan, kernel, projector.Stencil, counts) is None
    assert counts["unproved_projection_domain"] == 1
    scan.shifted = lambda: None
    assert compact_view(scan, kernel, projector.Stencil, counts) is None
    assert counts["unsupported_scan"] == 1
