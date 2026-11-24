"""Rotate one signed ECEF capsule through the released and successor discovery ports."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO
import json
from math import cos, radians, remainder, sin
from pathlib import Path
import runpy
import sys

import numpy as np


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
CAPSULE = Path("/dev/shm/leo-v3-curvature-shared-result02/dense-fixed-state.npz")
CAPSULE_SHA = "d5ea12467048f59146f35cba44e16886e83d80975e608333cef73fac05bc40ec"
OFFER = Path("/dev/shm/leo-dense-8ms-prefix-fit01/candidate/joint-research-receipt.json")
OFFER_SHA = "f70566671491da7eb1b5b572e60ffd5eb5ab65c398757de9e1e40137d2784c95"
SHARING = ROOT/"tools/pipeline_eval/variants/algo08_blind_rank.py"
SHARING_SHA = "321df8d3771fd478543e7c161a4b1c7d1a84734c8c4a0ae2768ebdf1c9038831"
PROJECTOR_SHA = "7a183da26216e8d86c571aef8e48f29bade29a2c3b34bde56b26aebfefe6059d"
ARMS = ("c0", "fitted_c")
OFFSETS = ((0., 0.), (-4., .75), (4., -.75), (-25., 0.), (25., 0.))
FIELDS = ("frequency_hz", "elevation_deg", "phase_derivative_hz_s", "fixed_family_raw_residual_hz")
LIMIT = {"frequency_hz": 1e-6, "elevation_deg": 1e-8, "phase_derivative_hz_s": 2e-6,
         "fixed_family_raw_residual_hz": 2e-6, "local_km": 1e-8}


def rotate_z(vectors, angle_deg):
    a = radians(angle_deg)
    c, s = cos(a), sin(a)
    x, y, z = np.moveaxis(vectors, -1, 0)
    return np.ascontiguousarray(np.stack((c*x - s*y, s*x + c*y, z), axis=-1))


def rotate_bank(bank, angle_deg):
    if angle_deg == 0.:
        return bank
    return dict(bank, position_km=rotate_z(bank["position_km"], angle_deg),
                velocity_km_s=rotate_z(bank["velocity_km_s"], angle_deg))


def relocated_offer(source, target_lon):
    result = dict(source)
    angle = remainder(target_lon - source["center"][1], 360.)
    result["center"] = (source["center"][0], target_lon)
    screen_lat, screen_lon = source["screen_center"]
    result["screen_center"] = (screen_lat, remainder(screen_lon + angle, 360.))
    return result, angle


def recorded_scene(checked):
    with np.load(BytesIO(checked(CAPSULE, CAPSULE_SHA)), allow_pickle=False) as packet:
        data = json.loads(packet["document"].item())
        bank = {key: packet[key] for key in ("time_s", "position_km", "velocity_km_s")}
    source = json.loads(checked(OFFER, OFFER_SHA))["receipt"]["region"]
    # The prespecified common rows with a previously audited alternative. Only
    # the identity roster and its two actual phase vectors enter this check.
    rows = data["layouts"]["changed_only"]
    times = np.concatenate([item["times"] for item in rows["rows"]])
    observed = np.concatenate([item["values"] for item in rows["rows"]])
    rf = np.repeat([item["rf_ratio"] for item in rows["rows"]], [len(item["times"]) for item in rows["rows"]])
    labels = np.array(rows["labels"][0], dtype=np.intp)
    phases = {arm: np.asarray(data["states"][arm][0]["posterior"], dtype=np.float64) for arm in ARMS}
    if times.shape != labels.shape or times.shape != observed.shape or set(rows["receivers"]) != {1, 2}:
        raise ValueError("The signed common observation roster changed")
    return bank, source, phases, (times, observed, rf, labels), len(rows["rows"])


def prepared_scan(region, screen, bank, all_times):
    from leo.analysis.localization_v3 import scan as kernel

    # These are the only fields read by ScanLikelihood.latlon/shifted and by
    # the current shared-ranking adapter. No reconstructed fit or catalogue.
    scan = object.__new__(kernel.ScanLikelihood)
    scan.search_region, scan.center, scan.sky = region, screen, bank
    scan.scale = 111.32 * np.cos(np.deg2rad(screen[0]))
    scan.times = all_times
    scan.geometry = kernel.prepare_phase_geometry(bank, all_times)
    return scan


def queries(scan, sparse_projection, sparse_pin, share, phases, measured):
    from leo.analysis.localization_v3 import discovery

    region = scan.search_region
    times, values, rf, labels = measured
    index = np.searchsorted(scan.times, times)
    directions, values_by_arm = [], {arm: [] for arm in ARMS}
    with share(scan) if share is not None else nullcontext() as cache:
        with sparse_projection(scan, expected_source_sha256=sparse_pin) as sparse:
            for xy in OFFSETS:
                coordinates = region.latlon(xy)
                native = region.native_point(scan, xy)
                shifted_site = scan.latlon(native)
                directions.append(dict(observer=coordinates, screen_xy_km=native.tolist(), shifted_site=shifted_site))
                source = discovery.phase_linear_frequency(scan.geometry, *coordinates)
                if xy == OFFSETS[0]:
                    repeat = discovery.phase_linear_frequency(scan.geometry, *coordinates)
                    if cache is not None and repeat is not source:
                        raise ValueError("The candidate did not reuse the real centre projection")
                for arm in ARMS:
                    result = tuple(np.asarray(a) for a in scan.shifted(source, phases[arm], native))
                    residual = values - rf * result[0][labels, index]
                    values_by_arm[arm].append((*result, residual))
    return directions, values_by_arm, dict(cache or {}), dict(sparse)


def maxima(reference, candidate):
    result = {}
    for arm in ARMS:
        pairs = list(zip(reference[arm], candidate[arm], strict=True))
        sizes = {k: max(float(np.max(np.abs(a[i] - b[i]))) for a, b in pairs) for i, k in enumerate(FIELDS)}
        visibility = sum(np.count_nonzero((a[1] >= 0) != (b[1] >= 0)) for a, b in pairs)
        equal = all(np.array_equal(x.view(np.uint64), y.view(np.uint64)) for a, b in pairs
                    for x, y in zip(a, b, strict=True))
        result[arm] = dict(maximum=sizes, visibility_differences=int(visibility), bit_identical=equal)
    return result


def unwrapped_control(scan, offset, project):
    coordinates = scan.search_region.latlon(offset)
    try:
        project(scan.geometry, *coordinates)
    except ValueError as error:
        return str(error)
    return None


def experiment():
    from empty_bootstrap import RELEASE, checked, clock, load_runtime, now
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    started = now()
    launcher, spec, _, publication, _ = load_runtime()
    from leo.analysis.localization_v3 import discovery
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.contracts.algo08_region import Algo08Region
    from tools.pipeline_eval.variants import orbit_projector, v5_direct_cavity
    from tools.pipeline_eval.variants.algo08_sparse_rank_projection import sparse_rank_projection
    from tools.pipeline_eval.variants.experimental.regional_reassignment import probes

    library = RELEASE/"assets/projector.so"
    checked(library, PROJECTOR_SHA)
    checked(SHARING, SHARING_SHA)
    share = runpy.run_path(str(SHARING))["shared_rank_preparation"]
    if spec.get("wrapped_longitude") is not True:
        raise ValueError("The named specification no longer enables the published chart")
    chart = publication._checked_longitude_chart(spec)
    projector = orbit_projector.Projector(library)
    bank, source, phases, measured, tracks = recorded_scene(checked)
    all_times = np.unique(measured[0])
    baseline, evidence = None, {}
    with v5_direct_cavity.numerical_bindings(projector):
        for name, longitude in (("source", source["center"][1]), ("ordinary", -18.5), ("east", 179.8), ("west", -179.8)):
            moved, angle = relocated_offer(source, longitude)
            accepted = Algo08Region.parse(moved)
            tile = SearchRegion(accepted.center, accepted.width_km)
            scan = prepared_scan(tile, accepted.screen_center, rotate_bank(bank, angle), all_times)
            before = [unwrapped_control(scan, xy, discovery.phase_linear_frequency) for xy in OFFSETS]
            unwrapped_east = float(tile.native_point(scan, (0., 0.))[0])
            with chart():
                book = {key: queries(scan, sparse_rank_projection, spec["sparse_rank_projection"], route, phases, measured)
                        for key, route in (("named", None), ("successor", share))}
                exterior = list(probes(tile))
            chart_rows, named, _, _ = book["named"]
            same = maxima(named, book["successor"][1])
            if chart_rows != book["successor"][0] or any(not row["bit_identical"] for row in same.values()):
                raise ValueError(f"The successor changed its released projection at {name}")
            if baseline is None:
                baseline, baseline_xy = named, np.array([r["screen_xy_km"] for r in chart_rows])
            rotational = maxima(baseline, named)
            xy_delta = float(np.max(np.abs(baseline_xy - [r["screen_xy_km"] for r in chart_rows])))
            if (xy_delta > LIMIT["local_km"] or any(r["visibility_differences"] or any(v > LIMIT[k]
                    for k, v in r["maximum"].items()) for r in rotational.values())):
                raise ValueError(f"The sealed rotational tolerance failed at {name}")
            evidence[name] = dict(offer=accepted.document(), rotation_deg=angle, queries=chart_rows, rotational=rotational,
                 candidate_vs_named=same, screen_xy_delta_km=xy_delta, unwrapped_center_east_km=unwrapped_east,
                 unwrapped_projection_errors=before, exterior_locations=len(exterior),
                 exterior_opposite_sign=sum(bool(np.sign(p["latlon"][1]) != np.sign(longitude)) for p in exterior),
                 counters={key: dict(centre=row[2], sparse=row[3]) for key, row in book.items()})
    return dict(case="DS30-0008", sources=dict(capsule=CAPSULE_SHA, offer=OFFER_SHA, sharing=SHARING_SHA,
                projector=PROJECTOR_SHA, specification=launcher["FINGERPRINT"], sparse=spec["sparse_rank_projection"],
                longitude_chart=spec["sources"][str(publication.LONGITUDE_CHART_SOURCE)]),
                offers=evidence, offsets_km=OFFSETS, tolerance=LIMIT, tracks=tracks, observations=len(measured[0]),
                satellites=len(bank["position_km"]), projector_calls=projector.calls, solve_calls=0, waveform_opens=0,
                clock=clock(started))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", type=Path)
    args = parser.parse_args()
    with args.receipt.open("x") as stream:
        json.dump(experiment(), stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
