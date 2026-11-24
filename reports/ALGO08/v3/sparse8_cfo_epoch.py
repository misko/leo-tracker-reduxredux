"""Compare the fixed 8 ms aperture prediction on already verified saved detector lanes."""

import argparse
from bisect import bisect_left
from collections import Counter, defaultdict
from hashlib import sha256
import json
from math import asin, cos, radians, remainder, sin, sqrt
from pathlib import Path
from statistics import mean

import numpy as np

from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.contracts.digests import canonical_digest
from sparse8_time_math import RATE, centroid


HERE = Path(__file__).resolve().parent
ROOT = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases")
ROSTER = HERE / "measurements/sparse8-cfo-epoch-roster.json"
CONFIG = Path("/opt/leo-algo08/current/assets/tracks.json")
STOCK = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
SHORT = "c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c"
RECIPE = "ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"
SCOUT = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse")
BUILD = Path("/var/tmp/leo-v3-eight-ms-build-padded")
FULL_SOURCE = Path("/var/tmp/leo-short-signed-02/control")
SOURCE_PINS = {
    SCOUT / "use.so": SHORT,
    SCOUT / "timing_first_receiver.c": "10d8ec75ac2d6e820dd9cee184b2825b8d6510a465bbb8bfa38fc782126daea5",
    BUILD / "8ms/two_carrier_receiver.c": "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e",
    BUILD / "scouts/8ms/portable_verifier.c": "bae3798db85b2682ae88d7ce545aac0d084c5f3a747d34cf5c43edd908e0996b",
    BUILD / "scouts/8ms/delay_product_kernel.c": "d4f199ee7fe3d5208d15887054982206f659d58988c086439cff3b0e62e2bbf5",
    FULL_SOURCE / "portable_verifier.c": "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707",
    FULL_SOURCE / "delay_product_kernel.c": "d014fe0670ff7a926bbd302ada1f4d021fe2f488f91b32dae8b4fe1634a07f1c",
}
ARMS = ("c0", "fitted_c")
PILOT_PERIOD = 13_333
ALIAS_HZ = RATE / 44


def digest(body):
    return sha256(body).hexdigest()


def checked(path, pin):
    body = path.read_bytes()
    if digest(body) != pin.removeprefix("sha256:"):
        raise ValueError(f"Saved receipt changed: {path}")
    return body


def read(path):
    return json.loads(path.read_bytes())


def t_frame(factor):
    return factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]


def fit_past(target_time, target_visit, donors):
    """Return frozen causal quadratic and linear slopes and a held-center stock prediction."""
    end = bisect_left(donors, (target_time,))
    selected = [(t-target_time, value) for t, visit, value in donors[max(0, end-6):end]
                if visit != target_visit and .025 <= target_time-t <= 8.]
    if len(selected) < 4 or selected[-1][0] < -3. or selected[-1][0]-selected[0][0] < .8:
        return None
    t, y = np.asarray(selected, dtype=float).T
    # Center at the target time and remove a constant carrier for conditioning only.
    delta = y[-1]
    design = np.column_stack((np.ones(len(t)), t, t*t))
    poly, _, rank, _ = np.linalg.lstsq(design, y-delta, rcond=None)
    if rank != 3 or np.max(abs(design@poly - (y-delta))) > 450. or abs(poly[1]) > 8000.:
        return None
    linear = np.linalg.lstsq(design[:, :2], y-delta, rcond=None)[0]
    return dict(slope_hz_per_s=float(poly[1]), linear_slope_hz_per_s=float(linear[1]),
                held_stock_prediction_hz=float(poly[0]+delta), donors=len(t), latest_donor_age_s=float(-t[-1]),
                donor_span_s=float(t[-1]-t[0]))


def observed_match(a, b):
    if len(a) != 1 or len(b) != 1:
        return None
    x, y = a[0], b[0]
    delta = y["fractional_tracking_cfo_hz"]-x["fractional_tracking_cfo_hz"]
    folded = remainder(delta, ALIAS_HZ)
    if not (x["passed_fractional_margin_gate"] and y["passed_fractional_margin_gate"]
            and x["candidate_rank"] == y["candidate_rank"] == 0
            and abs(remainder(t_frame(y)-t_frame(x), PILOT_PERIOD)) <= 2 and abs(folded) <= 250):
        return None
    return delta, folded, "signed" if abs(delta) <= 250 else "wrapped-only"


def native_packet(publication, result, detector):
    paths = tuple((publication / "fast-scan-automatic-work").glob("*/detections.json"))
    if not paths:
        raise FileNotFoundError("No saved native acquisition in the verified attempt")
    (path,) = paths
    native = read(path)
    source = native["source"]
    if (canonical_digest(native) != result["native_sha256"]
            or native["provenance"]["detector_sha256"] != "sha256:"+detector
            or source["analysis_manifest_sha256"] != canonical_digest(
                ["cancellation", source["raw_recording_authority_digest"], detector, source["probes"]])
            or source["sample_rate_hz"] != RATE or source["probe_ms"] != 20 or not source["qualified"]):
        raise ValueError("Saved native packet failed its original receiver or terminal binding")
    return native


def read_pair(case, spec):
    home = ROOT / case
    pair = json.loads(checked(home / "pair.json", spec["pair_sha256"]))
    if not pair["verified_pair"]:
        return None
    authority = json.loads(checked(home / "authority.json", pair["authority_sha256"]))
    results, packets, products = {}, {}, {}
    for mode, detector in (("installed", STOCK), ("successor", RECIPE)):
        folder = home / mode / f"attempt-{pair['generation']:06d}"
        result = json.loads(checked(folder / "result.json", pair["attempt_result_sha256"][mode]))
        if result["raw_identity"] != authority:
            raise ValueError("Pair attempts disagree on the original recording authority")
        publication = folder / "publication"
        try:
            packets[mode] = native_packet(publication, result, detector)
        except FileNotFoundError:
            return None
        source = packets[mode]["source"]
        if any(source[k] != authority[auth] for k, auth in (
            ("raw_recording_authority_digest", "raw_authority_sha256"), ("input_manifest_sha256", "inventory_sha256"),
            ("session_id", "session_id"))) or packets[mode]["clock_anchor"]["before"]["realtime_ns"] != authority["causal_cutoff_utc_ns"]:
            raise ValueError("Native packet was not produced by the paired timing authority")
        results[mode], products[mode] = result, publication
    b = read(products["successor"] / "unified-short-bootstrap.json")
    r = b["receiver_recipe"]
    if (canonical_digest(r) != "sha256:"+RECIPE or r["aperture_samples"] != [200_000, 80_000]
            or (r["installed_sha256"], r["shortened_sha256"]) != (STOCK, SHORT)
            or r["rule"] != ["full"]+["short_primary"]*7 or r["streams"] != ["edge", "channel", "actual_rf_hz"]
            or b["held_anchor_route"]["refinement_calls"] or b["held_anchor_route"]["choice"]["route"] != "unfiltered"):
        raise ValueError("The saved cadence or independent verifier recipe differs")
    witness = products["successor"] / "exact-named-raw-witness.json"
    owners = set()
    if results["successor"]["outcome"] == "complete" and witness.exists():
        w = read(witness)
        maps = {arm: {oid: norad for oid, norad, _ in w["evidence"]["owner_rows"][arm]} for arm in ARMS}
        if any(canonical_digest(maps[arm]) != results["successor"]["evidence"]["owners"][arm] for arm in ARMS):
            raise ValueError("The candidate owner stratum does not reproduce the published digests")
        owners = {oid for oid, norad in maps["c0"].items() if maps["fitted_c"].get(oid) == norad}
    return pair, packets, results, owners


def paired_lanes(stock, candidate):
    original, measured = (d["source"]["probes"] for d in (stock, candidate))
    if any(stock[k] != candidate[k] for k in ("clock_anchor", "delivery_clocks", "last_sample_counter")):
        raise ValueError("Receiver outputs changed original hardware clocks")
    if stock["provenance"]["excluded_windows"] != candidate["provenance"]["excluded_windows"]:
        raise ValueError("Receiver outputs changed original capture exclusions")
    streams, result = Counter(), {}
    session = stock["source"]["session_id"]
    anchor = stock["clock_anchor"]
    not_yet_paired = None
    for a, b in zip(original, measured, strict=True):
        if dict(a, candidates=[]) != dict(b, candidates=[]):
            raise ValueError("The two receivers changed original opportunity coordinates")
        visit, receiver, start = (a[k] for k in ("visit_index", "receiver_id", "valid_start_counter"))
        stream = tuple(a[k] for k in ("edge", "channel", "actual_rf_hz"))
        peer = visit, start, stream
        if receiver == 0 and not_yet_paired is None:
            not_yet_paired = peer
            full = streams[stream] % 8 == 0
            streams[stream] += 1
        elif receiver == 1 and peer == not_yet_paired:
            not_yet_paired = None
        else:
            raise ValueError("Expected each original stereo visit in receiver order")
        oid = "sha256:" + digest(f"{session}:{receiver}:{start}".encode())
        if oid in result:
            raise ValueError("Original clock repeated a receiver opportunity")
        time_s = (start-anchor["sample_counter"]) / RATE + .010
        result[oid] = (visit, receiver, stream, time_s, full, a, b)
    if not_yet_paired is not None:
        raise ValueError("Incomplete stereo source")
    return result


def graph_donors(stock, config, lanes):
    output = {}
    tracks = prepare_tracks(stock, config)["tracks"]
    for track in tracks:
        rows = list(zip(track["observation_ids"], map(float, track["times"]), map(float, track["values"]), strict=True))
        for piece in track["pieces"]:
            members = [(oid, t, value) for oid, t, value in rows if piece["start_s"] <= t <= piece["end_s"]]
            donors = [(t, lanes[oid][0], value) for oid, t, value in members]
            for oid, t, value in members:
                if oid in output or abs(t-lanes[oid][3]) > 1e-12:
                    raise ValueError("Stock graph identity or saved observation time disagrees")
                output[oid] = (track["key"], value, donors)
    return output


def summary(points):
    if not points:
        return dict(n=0)
    actual, predicted = (np.asarray([p[key] for p in points], dtype=float) for key in ("observed_hz", "prediction_hz"))
    delta = actual-predicted
    mse = float(np.mean(actual**2))
    return dict(n=len(points), observed_rms_hz=sqrt(mse), predicted_rms_hz=float(np.sqrt(np.mean(predicted**2))),
                predicted_p95_abs_hz=float(np.quantile(abs(predicted), .95)),
                predicted_max_abs_hz=float(np.max(abs(predicted))), corrected_rms_hz=float(np.sqrt(np.mean(delta**2))),
                reversed_rms_hz=float(np.sqrt(np.mean((actual+predicted)**2))),
                mse_reduction=(float(1-np.mean(delta**2)/mse) if mse else None),
                through_origin_measured_scale=(float(actual@predicted/(predicted@predicted)) if np.any(predicted) else None),
                median_shift_ms=float(np.median([p["epoch_shift_ms"] for p in points])),
                linear_corrected_rms_hz=float(np.sqrt(np.mean([(p["observed_hz"]-p["linear_prediction_hz"])**2 for p in points]))),
                held_stock_extrapolation_rms_hz=float(np.sqrt(np.mean([p["held_stock_residual_hz"]**2 for p in points]))),
                same_sign=float(np.mean(actual*predicted > 0)),
                quadratic_linear_same_sign=float(np.mean([p["prediction_hz"]*p["linear_prediction_hz"] > 0 for p in points])))


def compare(stock, candidate, owners, config):
    lanes = paired_lanes(stock, candidate)
    donor_map = graph_donors(stock, config, lanes)
    counts, anchors, wrapped, rows = Counter(), [], [], []
    for oid, (visit, rx, (edge, channel, rf), t, full, a, b) in lanes.items():
        label = "anchor" if full else "short"
        counts[label+"_scheduled"] += 1
        av, bv = a["candidates"], b["candidates"]
        counts[label+"_"+("both" if av and bv else "installed_only" if av else "candidate_only" if bv else "neither")] += 1
        match = observed_match(av, bv)
        if match is None:
            continue
        raw, folded, kind = match
        counts[label+"_"+kind] += 1
        if kind == "wrapped-only":
            wrapped.append(dict(observation_id=oid, visit=visit, receiver=rx, channel=channel, anchor=full,
                                observed_hz=raw, folded_hz=folded, alias_integer=round((raw-folded)/ALIAS_HZ)))
            continue
        if full:
            anchors.append(raw)
            if av == bv:
                counts["anchor_exact_factor"] += 1
        if oid not in donor_map:
            continue
        track, actual, donors = donor_map[oid]
        fit = fit_past(t, visit, donors)
        if fit is None:
            continue
        x, frames, dx = centroid(av[0], False)
        y, short_frames, dy = centroid(bv[0], not full)
        shift = y-x
        row = dict(observation_id=oid, visit=visit, receiver=rx, channel=channel, edge=edge, rf_hz=rf,
                   time_s=t, anchor=full, candidate_owned_both_arms=oid in owners, stock_track=track,
                   stock_frames=frames, successor_frames=short_frames, observed_hz=raw, epoch_shift_ms=1000*shift,
                   full_effective_from_valid_start_ms=1000*x, successor_effective_from_valid_start_ms=1000*y,
                   prediction_hz=shift*fit["slope_hz_per_s"],
                   delay_support_prediction_hz=(dy-dx)*fit["slope_hz_per_s"],
                   linear_prediction_hz=shift*fit["linear_slope_hz_per_s"],
                   held_stock_residual_hz=actual-fit["held_stock_prediction_hz"], **fit)
        rows.append(row)
    return dict(counts=counts, strict_anchor_max_abs_hz=max(map(abs, anchors), default=None), rows=rows,
                wrapped_alias_comparisons=wrapped)


def predict():
    for source, pin in SOURCE_PINS.items():
        checked(source, pin)
    cfg = CONFIG.read_bytes()
    config = TrackConfig(**json.loads(cfg)["config"])
    if config.alias_spacing_hz != ALIAS_HZ:
        raise ValueError("Unexpected Graph alias convention")
    cases, holdout = {}, []
    for case, spec in read(ROSTER).items():
        item = read_pair(case, spec)
        if item is None:
            cases[case] = dict(status="unverified pair or missing native acquisition")
            continue
        pair, packets, results, owners = item
        result = compare(packets["installed"], packets["successor"], owners, config)
        short = [r for r in result["rows"] if not r["anchor"]]
        result.update(status="verified saved acquisitions", development=case == "DS30-0049",
                      native={mode: doc["native_sha256"] for mode, doc in results.items()},
                      outcomes={mode: doc["outcome"] for mode, doc in results.items()},
                      short=summary(short), short_candidate_owned=summary([p for p in short if p["candidate_owned_both_arms"]]),
                      stock_extrapolates_within_graph_gate=summary([p for p in short if abs(p["held_stock_residual_hz"]) <= 450]),
                      by_lane={f"rx{r}/ch{ch}": summary([p for p in short if (p["receiver"], p["channel"]) == (r, ch)])
                               for r, ch in sorted({(p["receiver"], p["channel"]) for p in short})})
        if case != "DS30-0049":
            holdout.extend(short)
        cases[case] = result
    summaries = [r["short"]["mse_reduction"] for r in cases.values() if r.get("development") is False and r["short"]["n"]]
    return dict(schema="leo.research.sparse8-cfo-epoch.v1", input_roster_sha256=digest(ROSTER.read_bytes()),
                dsp_sources={str(path): pin for path, pin in SOURCE_PINS.items()}, graph_config_sha256=digest(cfg),
                cases=cases, holdout=summary(holdout), holdout_equal_capture_mse_reduction=mean(summaries),
                holdout_captures_improving=sum(x > 0 for x in summaries), holdout_captures=len(summaries),
                survey_reads=0, receiver_workers=0, solver_workers=0, waveform_reads=0)


def compare_published(prediction, pin):
    cohort = json.loads(checked(prediction, pin))
    results = {}
    for case, row in cohort["cases"].items():
        if "short" not in row:
            continue
        home = ROOT / case
        pair = json.loads(checked(home / "pair.json", read(ROSTER)[case]["pair_sha256"]))
        arms = {}
        for mode in ("installed", "successor"):
            p = home / mode / f"attempt-{pair['generation']:06d}" / "result.json"
            doc = json.loads(checked(p, pair["attempt_result_sha256"][mode]))
            arms[mode] = doc["evidence"]["arms"]
        witness = {}
        for arm in ARMS:
            a, b = (arms[mode].get(arm, {}) for mode in ("installed", "successor"))
            p, q = a.get("latlon"), b.get("latlon")
            dist = None
            if p is not None and q is not None:
                x, y = map(radians, p)
                u, v = map(radians, q)
                dist = 12742.0176*asin(sqrt(sin((x-u)/2)**2+cos(x)*cos(u)*sin((y-v)/2)**2))
            witness[arm] = dict(installed_rf_rms_hz=a.get("rf_rms_hz"), successor_rf_rms_hz=b.get("rf_rms_hz"),
                                published_endpoint_separation_km=dist)
        results[case] = witness
    return dict(prediction_sha256=pin, cases=results, survey_reads=0, position_refits=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("predict", "published"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--prediction-sha256")
    args = parser.parse_args()
    result = predict() if args.mode == "predict" else compare_published(args.predictions, args.prediction_sha256)
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, allow_nan=False)
        stream.write("\n")
