"""Compare installed and native regional Doppler kernels on one public field capture."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import runpy
import sys


HERE = Path(__file__).resolve().parent
DATA = HERE.parents[1] / "2026_11_18_blind_regional_receiver"
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
LAUNCHER = Path("/opt/leo-algo08/algo08v3/run")
LAUNCHER_PIN = "fae032526227f55ca2419a0b29c69afc7fc97fa04508f33d0403802934f13448"
MANIFEST_PIN = "62f00440854e7c05eed63d3713d7c2a7578ea6eca604bcab0b0b57133014e341"
LIBRARY = Path("/dev/shm/leo-v3-saved-0402-pair-01/geographic_library.so")
LIBRARY_PIN = "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee"
TOLERANCE = 1e-6  # Hz and Hz/s separately, same tolerance for centered RF RMS.
CAPTURE_COUNT = 11
SHAPE_SAMPLES = 12
MAX_AGE_NS = 48 * 3600 * 10**9
FIELD_RF_HZ = 11325000000.0
HEIGHT_M = 0.0


def checked(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Unexpected bytes for {path.name}")
    return data


def opaque_key(digest):
    return sha256(f"physical-kernel-v1/{digest}".encode()).digest()


def enroll(field, receipt):
    if receipt["public_manifest_sha256"] != MANIFEST_PIN:
        raise ValueError("Expected the original sealed StarLoc public inventory")
    roster = json.loads(checked(field / "manifest.json", MANIFEST_PIN))["queries"]
    if len(roster) != 2 * CAPTURE_COUNT or set(roster) != set(receipt["public_query_sha256"]):
        raise ValueError("Expected all original opaque query labels")
    groups = defaultdict(list)
    for id_ in roster:
        row = json.loads(checked(field / "queries" / f"{id_}.json", receipt["public_query_sha256"][id_]))
        if id_ != row["id"] or len(row["regions"]) != 4:
            raise ValueError("Original supplied query shape changed")
        groups[row["observation"]].append(row)
    if len(groups) != CAPTURE_COUNT or any(len(rows) != 2 or len({row["catalog"] for row in rows}) != 1
                                            for rows in groups.values()):
        raise ValueError("Expected the original two offers on each physical packet")
    key = min(groups, key=opaque_key)
    return key, sorted(groups[key], key=lambda row: row["id"])


def centered(values):
    return values - values.mean(axis=-1, keepdims=True)


def shape_metrics(measured, predicted, tangent):
    """Profile the archive's anonymous tone offset and bounded orbit phase."""
    import numpy as np

    # These are the external StarLoc panel's pre-existing score scales. They
    # are not calibrated GLRT uncertainties or probabilistic decision gates.
    shape_hz, scale_s, limit_s = 180.0, 2.0, 8.0
    difference = centered(measured) - centered(predicted)
    slope = centered(tangent)
    phase = np.clip(np.mean(difference * slope, axis=-1) /
                    (np.mean(slope * slope, axis=-1) + (shape_hz / scale_s)**2), -limit_s, limit_s)
    rms = np.sqrt(np.mean((difference - phase[:, None] * slope)**2, axis=-1))
    return (rms / shape_hz)**2 + (phase / scale_s)**2, rms


def causal_catalogue(tle, observation):
    from leo.sky.propagation import ElementSetCatalogue, parse_element_sets

    start = observation["anchor_utc_ns"]
    cutoff = observation["cutoff_utc_ns"]
    snapshot = observation["catalog_timestamp_ns"]
    if snapshot > cutoff or cutoff > start:
        raise ValueError("Orbit availability must precede or tie the archived cutoff")
    source = parse_element_sets(tle.decode("utf-8"))
    latest = {}
    for index, (number, epoch) in enumerate(zip(source.satellite_numbers, source.element_epoch_utc_ns(), strict=True)):
        if cutoff - MAX_AGE_NS <= epoch <= snapshot and (number not in latest or epoch > latest[number][0]):
            latest[number] = epoch, index
    if not latest:
        raise ValueError("No in-window orbital elements for the original capture")
    rows = [latest[number][1] for number in sorted(latest)]
    return ElementSetCatalogue(tuple(source.names[i] for i in rows), tuple(source.satellite_numbers[i] for i in rows),
                               tuple(source.satellites[i] for i in rows)), len(source)


def measured_tracks(observation):
    import numpy as np

    output = []
    for track in observation["tracks"]:
        times = np.asarray(track["times"], dtype=np.float64)
        values = np.asarray(track["values"], dtype=np.float64)
        if (track["rf_hz"] != FIELD_RF_HZ or track["channel"] != 3 or track["receiver"] != 1
                or values.ndim != 1 or values.shape != times.shape or len(times) < 4
                or not np.isfinite(times).all() or not np.isfinite(values).all() or not (np.diff(times) > 0).all()
                or times[0] < 0 or times[-1] > observation["duration_s"]):
            raise ValueError("Unexpected StarLoc anonymous pooled track contract")
        take = np.rint(np.linspace(0, len(times) - 1, min(len(times), SHAPE_SAMPLES))).astype(int)
        output.append((times[take], values[take], len(times)))
    return output


def compare(reference, candidate, tracks, satnums):
    import numpy as np

    frequency, elevation, derivative = reference
    faster, horizon, tangent = candidate
    visible = elevation >= 0
    if horizon.dtype != np.int8 or not np.array_equal(visible, horizon >= 0):
        raise ValueError("Native and installed visible-horizon masks differ")
    frequency_error = float(np.max(np.abs(frequency - faster)))
    derivative_error = float(np.max(np.abs(derivative - tangent)))
    if max(frequency_error, derivative_error) > TOLERANCE:
        raise ValueError("Native and installed physical Doppler quantities differ")
    summaries = []
    first = 0
    for _, observed_hz, _ in tracks:
        columns = slice(first, first + len(observed_hz))
        first = columns.stop
        mask = visible[:, columns].all(axis=1)
        model, orbit_tangent = frequency[mask, columns], derivative[mask, columns]
        if not mask.any():
            summaries.append(dict(visible_candidates=0))
            continue
        loss, rms = shape_metrics(observed_hz, model, orbit_tangent)
        nloss, nrms = shape_metrics(observed_hz, faster[mask, columns], tangent[mask, columns])
        named_best, native_best = np.argmin(loss), np.argmin(nloss)
        loss_error = float(np.max(np.abs(loss - nloss)))
        rms_error = float(np.max(np.abs(rms - nrms)))
        # One RF per anonymous track leaves c indistinguishable from its
        # constant nuisance, including any constant center-tone ambiguity.
        offset = 100000.0 * ((FIELD_RF_HZ - 11.5e9) / 1e9)
        _, gauge_rms = shape_metrics(observed_hz, model + offset, orbit_tangent)
        gauge_error = float(np.max(np.abs(rms - gauge_rms)))
        if named_best != native_best or max(loss_error, rms_error, gauge_error) > TOLERANCE:
            raise ValueError("Comparator disagrees after the original anonymous tone nuisance")
        order = np.sort(loss, kind="stable")
        summaries.append(dict(visible_candidates=int(mask.sum()),
                              diagnostic_lowest_loss_norad=int(satnums[mask][named_best]),
                              best_centered_rf_rms_hz=float(rms[named_best]),
                              best_loss=float(loss[named_best]),
                              second_minus_best_loss=float(order[1] - order[0]) if len(order) > 1 else None,
                              max_shape_rms_disagreement_hz=rms_error, max_shape_loss_disagreement=loss_error,
                              max_fixed_rf_c_gauge_disagreement_hz=gauge_error))
    return dict(max_frequency_disagreement_hz=frequency_error, max_phase_derivative_disagreement_hz_s=derivative_error,
                horizon_sign_agrees=True, tracks=summaries)


def run(field, receipt_path, library):
    import numpy as np

    receipt = json.loads(receipt_path.read_bytes())
    digest, queries = enroll(field, receipt)
    observation = json.loads(checked(field / "observations" / f"{digest}.json", digest))
    catalog = queries[0]["catalog"]
    tle_bytes = checked(field / "orbits" / f"{catalog}.tle", catalog)
    tracks = measured_tracks(observation)
    if not tracks:
        raise ValueError("The prospectively selected capture has no accepted measured tones")

    checked(LAUNCHER, LAUNCHER_PIN)
    payload = LAUNCHER.resolve().parent / "payload"
    launcher = runpy.run_path(str(LAUNCHER))
    launcher["checked_spec"](payload)
    sys.path[:0] = list(map(str, (payload, RELEASE / "src", RELEASE)))
    from dense_geographic_projection import Projector, checked_runtime

    kernel, phase = checked_runtime()
    if Path(kernel.__file__).resolve() != payload / "tools/pipeline_eval/variants/experimental/regional_reassignment.py":
        raise ValueError("The regional reference did not resolve inside installed ALGO08v3")
    catalogue, initial_count = causal_catalogue(tle_bytes, observation)
    regions = [tile for query in queries for tile in query["regions"]]
    centers = [tuple(tile["center"]) for tile in regions]
    merged_times = np.concatenate([times for times, _, _ in tracks])
    # The installed setup expects chronological knots and the first track
    # times sorted. Remap its ordered columns back to each original track.
    ordered, mapping = np.unique(merged_times, return_inverse=True)
    starts = np.unique([times[0] for times, _, _ in tracks])
    geometry, satellite_numbers = kernel.orbit_geometry(catalogue, observation["anchor_utc_ns"],
                                                       ordered, starts, centers[0], centers)
    if geometry is None:
        raise ValueError("No original causal orbit has usable regional geometry")
    native = Projector(library, LIBRARY_PIN, phase)
    results = {}
    for row in queries:
        tiles = {}
        for tile in row["regions"]:
            kwargs = dict(altitude_m=HEIGHT_M, rf_hz=FIELD_RF_HZ)
            original = phase(geometry, *tile["center"], **kwargs)
            accelerated = native(geometry, *tile["center"], **kwargs)
            tiles[tile["id"]] = compare(tuple(x[:, mapping] for x in original),
                                        tuple(x[:, mapping] for x in accelerated), tracks, satellite_numbers)
        results[row["id"]] = tiles
    if native.counts["calls"] != len(regions) or native.counts["original_fallback"]:
        raise ValueError("The actual native projector must succeed on all unchanged supplied centers")
    return dict(observation_sha256=digest, catalogue_sha256=catalog, installed_spec=launcher["FINGERPRINT"],
                installed_launcher_sha256=LAUNCHER_PIN, native_library_sha256=LIBRARY_PIN,
                native_projection_counts={key: native.counts[key] for key in ("calls", "cells", "original_fallback")},
                rf_hz=FIELD_RF_HZ, reference_height_m=HEIGHT_M, anchor_utc_ns=observation["anchor_utc_ns"],
                cutoff_utc_ns=observation["cutoff_utc_ns"], availability_bound_ns=observation["catalog_timestamp_ns"],
                catalogue_rows=initial_count, retained_causal_satellites=len(catalogue), screened_satellites=len(satellite_numbers),
                measured_tracks=len(tracks), available_points=sum(original for _, _, original in tracks),
                used_points=sum(len(times) for times, _, _ in tracks), distinct_times=len(ordered), offers=results,
                max_tolerance=TOLERANCE, signed_frequency_hz=True, calibration_coefficient_identifiable=False,
                scope="regional physical geometry and external centered tone diagnostics only")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    cli.add_argument("--field-receipt", type=Path, default=DATA / "field-receipt.json")
    args = cli.parse_args()
    result = run(DATA / "public_field", args.field_receipt, LIBRARY)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
