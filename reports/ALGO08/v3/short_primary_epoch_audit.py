"""Audit an aperture-centroid time shift using only sealed short and stock factors."""

import argparse
from collections import Counter, defaultdict
import gzip
from hashlib import sha256
import json
from math import asin, cos, radians, remainder, sin, sqrt
from pathlib import Path

import numpy as np

from leo.analysis.localization_v3.tracks import prepare_tracks
from leo.analysis.polynomial_tracklets import TrackConfig
from leo.contracts.digests import canonical_digest
from leo.presentation.localization_v3 import owner_digest
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

ARMS = ("c0", "fitted_c")
PAID_KEYS = ("visit_index", "valid_start_counter", "channel", "actual_rf_hz", "edge")
SAMPLE_RATE = 10_000_000
FRAME_SAMPLES = 13_333
STOCK = "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
SHORT = "sha256:13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40"
OWNERS_SHA = "9ab0632563cc2ceacd043569956ef7fa1dfb9e24f26de370df57b8a19681221f"
RECEIVER_SOURCES = {
    "control/timing_first_receiver.c": "936b67cbb9af0201a7e65281756cc9c16f042ac2ad5e84201b1577131c67044a",
    "control/delay_product_kernel.c": "d014fe0670ff7a926bbd302ada1f4d021fe2f488f91b32dae8b4fe1634a07f1c",
    "control/portable_verifier.c": "3f62918238ad9107474d2f1509e953c61776eb70123ecd880c514f6e6483a707",
    "short/timing_first_receiver.c": "a8fa28b5997ee7b4537ebaca4e41982b4976de4b00fde82011871570a616e1cc",
    "short/delay_product_kernel.c": "944d8a9bfee130f8f12e22098ced20195464783e521ced9172c039cadb198ba2",
    "short/portable_verifier.c": "4cceaa68fe8d7f93608d1d07f585e2bc5c68955a22619d989052d6cde2e70def",
}
SHORT_ENTRY_SHA = "6f21e36a55caa489f5992a3fbae6006c2af549c30753b7053fae926d0cefb48e"
HERE = Path(__file__).resolve().parent
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
PANEL = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/publications")
PHYSICAL = Path("/var/tmp/leo-full-short-DS30-0016-pair")
CASES = {
    "DS30-0016": (PHYSICAL / "stock", PHYSICAL / "candidate", None),
    "south-containing": (BENCH / "exact-curved-lookahead-south-inside/candidate",
                         Path("/var/tmp/leo-full-short-south-transfer-final/containing"), "south-containing"),
    "DS30-0008": (PANEL / "DS30-0008/candidate",
                  Path("/var/tmp/leo-full-short-dense-DS30-0008/publication"), "DS30-0008"),
}


def read(path):
    return json.loads(path.read_bytes())


def load(directory, detector):
    automatic = directory / "fast-scan-automatic-work"
    native_path, = automatic.glob("*/detections.json")
    terminal_path, = automatic.glob("*/terminal.json")
    terminal, native = read(terminal_path), read(native_path)
    source = native["source"]
    raw = source["raw_recording_authority_digest"]
    if (terminal["native_sha256"] != canonical_digest(native)
            or terminal["session_id"] != source["session_id"]
            or native["provenance"]["detector_sha256"] != detector
            or source["analysis_manifest_sha256"] != canonical_digest(
                ["cancellation", raw, detector.removeprefix("sha256:"), source["probes"]],
            ) or source["sample_rate_hz"] != SAMPLE_RATE or source["probe_ms"] != 20.):
        raise ValueError("Terminal and native receiver packet disagree")
    if (directory / "joint-research-receipt.json").exists():
        receipt = read(directory / "joint-research-receipt.json")
        expected = receipt["receipt"]["terminal_sha256"]
        owners = receipt["selected_rows"]
        run_id = receipt["receipt"]["run_id"]
        manifest = read(FastStandardAnalysisStore(directory).folder(run_id) / "manifest.json")
        if manifest["terminal_sha256"] != expected:
            raise ValueError("Published owner manifest refers to another terminal")
        for arm in ARMS:
            data = {oid: norad for oid, norad, _ in owners[arm]}
            if (len(data) != len(owners[arm]) or len(data) != manifest["arms"][arm]["associated_points"]
                    or owner_digest(data) != manifest["arms"][arm]["owner_sha256"]):
                raise ValueError("Owner rows do not match the sealed publication manifest")
    else:
        expected = read(directory.parent / "pair.json")["runs"]["candidate"]["receipt"]["terminal_sha256"]
        owners = None
    if expected != canonical_digest(terminal) or terminal["decision"] != "ok":
        raise ValueError("Expected a sealed successful publication")
    return native, owners, terminal


def original_owners(path, name, native):
    content = path.read_bytes()
    if sha256(content).hexdigest() != OWNERS_SHA:
        raise ValueError("Unexpected archived stock owner census")
    receipt = json.loads(gzip.decompress(content))["runs"][name]["stock"]
    if receipt["identity"]["native_sha256"] != canonical_digest(native):
        raise ValueError("Archived stock owners refer to different native factors")
    for arm in ARMS:
        items = receipt["selected_rows"][arm]
        owners = {oid: norad for oid, norad, _ in items}
        if len(owners) != len(items) or owner_digest(owners) != receipt["owners"][arm]:
            raise ValueError("Archived owner rows do not match the sealed owner digest")
    return receipt["selected_rows"]


def both_arms(rows):
    a, b = ({oid: norad for oid, norad, _ in rows[arm]} for arm in ARMS)
    return {oid: sat for oid, sat in a.items() if b.get(oid) == sat}


def selected(probe):
    winners = [item for item in probe["candidates"] if item["passed_fractional_margin_gate"] is True]
    return max(winners, key=lambda item: (item["fractional_margin"], -item["candidate_rank"]), default=None)


def paired_probes(stock, candidate):
    left, right = stock["source"], candidate["source"]
    keys = ("session_id", "raw_recording_authority_digest", "input_manifest_sha256")
    if any(left[k] != right[k] for k in keys) or stock["clock_anchor"] != candidate["clock_anchor"]:
        raise ValueError("Receiver packets use different radio input or clock authority")
    rows, stream_slots = [], Counter()
    for i, (a, b) in enumerate(zip(left["probes"], right["probes"], strict=True)):
        if dict(a, candidates=[]) != dict(b, candidates=[]):
            raise ValueError("Receiver lane or valid start counter differs")
        if i % 2 == 0:
            peer = left["probes"][i+1]
            if (a["receiver_id"], peer["receiver_id"]) != (0, 1) or any(a[k] != peer[k] for k in PAID_KEYS):
                raise ValueError("Both original stereo opportunities are required")
            stream = tuple(a[k] for k in PAID_KEYS[2:])
            short = stream_slots[stream] % 8 != 0
            stream_slots[stream] += 1
        a_factor, b_factor = selected(a), selected(b)
        if short and b_factor is not None and b_factor["candidate_rank"] != 0:
            raise ValueError("Short-primary slot contains a residual factor")
        oid = "sha256:" + sha256(f"{left['session_id']}:{a['receiver_id']}:{a['valid_start_counter']}".encode()).hexdigest()
        rows.append((oid, a, a_factor, b_factor, short))
    return rows


def epoch(factor):
    return factor["integer_epoch_sample"] + factor["fractional_epoch_offset_samples"]


def good_match(stock, candidate):
    if stock is None or candidate is None:
        return False
    return (stock["candidate_rank"] == candidate["candidate_rank"] == 0
            and abs(remainder(epoch(candidate) - epoch(stock), FRAME_SAMPLES)) <= 2.
            and abs(candidate["fractional_tracking_cfo_hz"] - stock["fractional_tracking_cfo_hz"]) <= 250.)


def centroid(factor, *, short):
    """Equal-frame centroid of the source's actual fractional verifier support."""
    base, offset = (factor[k] for k in ("integer_epoch_sample", "fractional_epoch_offset_samples"))
    sample_count, max_frames = (120_000, 8) if short else (200_000, 15)
    integer = abs(offset - round(offset)) <= 1e-12
    starts = []
    for frame in range(max_frames):
        begin = base + (40_000 * frame + 1) // 3 + offset + 88
        if begin < (0 if integer else 7) or begin + 64 * 44 - 1 >= sample_count - (0 if integer else 8):
            break
        starts.append(begin)
    if not starts:
        raise ValueError("Selected factor has no fractional verifier support")
    return (float(np.mean(starts)) + (64 * 44 - 1) / 2) / SAMPLE_RATE, len(starts)


def slope(target_time, target_visit, donors):
    """One centered quadratic on bounded bracketing visits, excluding the whole target visit."""
    left, right = [], []
    for time, visit, value in donors:
        delta = time - target_time
        if visit == target_visit or delta == 0. or abs(delta) > 8.:
            continue
        (left if delta < 0. else right).append((delta, value))
    left.sort(reverse=True)
    right.sort()
    if min(len(left), len(right)) < 2 or min(-left[0][0], right[0][0]) < .025:
        return None
    if max(-left[0][0], right[0][0]) > 3.:
        return None
    x, y = np.asarray(left[:6] + right[:6], float).T
    if np.ptp(x) < .8:
        return None
    design = np.column_stack((np.ones(len(x)), x, x*x))
    fit, _, rank, _ = np.linalg.lstsq(design, y, rcond=None)
    if rank != 3 or np.max(np.abs(design @ fit - y)) > 450. or abs(fit[1]) > 8000.:
        return None
    return float(fit[1]), len(x)


def stats(values):
    if not len(values):
        return {"n": 0}
    x = np.asarray(values, float)
    return dict(n=len(x), median=float(np.median(x)), rms=float(np.sqrt(np.mean(x*x))),
                p95_abs=float(np.quantile(abs(x), .95)), maximum_abs=float(np.max(abs(x))))


def fit_summary(points):
    if not points:
        return dict(n=0)
    observed = np.asarray([p["change_hz"] for p in points])
    prediction = np.asarray([p["centroid_hz"] for p in points])
    correct = np.sign(observed) == np.sign(prediction)
    error_squared = float(observed @ observed)
    return dict(n=len(points), measured=stats(observed), centroid_prediction=stats(prediction),
                nominal_midpoint_prediction=stats([-.004 * p["slope_hz_s"] for p in points]),
                corrected=stats(observed-prediction),
                polarity_reversed=stats(observed+prediction), sign_agreement=float(correct.mean()),
                mse_reduction=None if error_squared == 0 else float(1 - np.sum((observed-prediction)**2)/error_squared),
                correlation=None if not np.std(observed) or not np.std(prediction)
                else float(np.corrcoef(observed, prediction)[0, 1]),
                window_bound_20ms_hz=stats([.020 * p["slope_hz_s"] for p in points]),
                source_shift_ms=stats([p["centroid_shift_ms"] for p in points]),
                support_counts=dict(Counter(str(p["full_frames"]) for p in points)))


def compare(stock, candidate, stock_owners, short_owners, config):
    pairs = paired_probes(stock, candidate)
    rows = {oid: (probe, a, b, short) for oid, probe, a, b, short in pairs}
    if len(rows) != len(pairs):
        raise ValueError("Native packet repeated an observation identity")
    installed_track = {}
    for track in prepare_tracks(stock, config)["tracks"]:
        for oid, time, value in zip(track["observation_ids"], track["times"], track["values"], strict=True):
            installed_track[oid] = (track["key"], float(time), float(value))
    donors = defaultdict(list)
    for oid, (track, t, value) in installed_track.items():
        if oid in stock_owners:
            visit = rows[oid][0]["visit_index"]
            donors[(track, stock_owners[oid])].append((t, visit, value))
    outcomes, counts, points = defaultdict(list), Counter(), []
    for oid, probe, a, b, short in pairs:
        scope = "short" if short else "full_anchor"
        counts[scope + "_lanes"] += 1
        if a is None or b is None:
            continue
        observed = b["fractional_tracking_cfo_hz"] - a["fractional_tracking_cfo_hz"]
        outcomes[scope + "_both"].append(observed)
        if not good_match(a, b):
            continue
        outcomes[scope + "_co_matched_primary"].append(observed)
        if oid not in stock_owners or stock_owners[oid] != short_owners.get(oid):
            continue
        outcomes[scope + "_same_satellite_both_arms"].append(observed)
        if not short or oid not in installed_track:
            continue
        track, time, _ = installed_track[oid]
        visit = probe["visit_index"]
        witness = slope(time, visit, donors[(track, stock_owners[oid])])
        if witness is None:
            continue
        dfdt, donor_count = witness
        full_center, frame_count = centroid(a, short=False)
        short_center, _ = centroid(b, short=True)
        dt = short_center - full_center
        points.append(dict(observation_id=oid, visit=visit, norad=stock_owners[oid],
                           track=track, donor_count=donor_count, slope_hz_s=dfdt,
                           change_hz=observed, centroid_hz=dt*dfdt,
                           centroid_shift_ms=1000.*dt, full_frames=frame_count))
    return dict(lanes=dict(counts), comparisons={k: stats(v) for k, v in sorted(outcomes.items())},
                temporal_model=fit_summary(points), tracks_used=len({p["track"] for p in points}),
                row_digest=canonical_digest(points))


def published_separation(stock, short):
    a, b = (tuple(map(radians, endpoint["latlon"])) for endpoint in (stock, short))
    h = sin((a[0]-b[0])/2)**2 + cos(a[0])*cos(b[0])*sin((a[1]-b[1])/2)**2
    return 2 * 6371.0088 * asin(sqrt(min(1., h)))


def source_identity(receiver_source, short_entry):
    actual = {name: sha256((receiver_source / name).read_bytes()).hexdigest() for name in RECEIVER_SOURCES}
    if actual != RECEIVER_SOURCES or sha256(short_entry.read_bytes()).hexdigest() != SHORT_ENTRY_SHA:
        raise ValueError("Receiver source differs from the reviewed aperture and epoch convention")
    return dict(dsp=actual, short_entry=SHORT_ENTRY_SHA)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--track-config", type=Path, required=True)
    parser.add_argument("--receiver-source", type=Path, default=Path("/var/tmp/leo-short-signed-02"))
    parser.add_argument("--short-entry", type=Path, default=Path(
        "/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2/two_carrier_receiver.c",
    ))
    parser.add_argument("--case", action="append", choices=tuple(CASES), default=[])
    args = parser.parse_args()
    config_bytes = args.track_config.read_bytes()
    config = TrackConfig(**json.loads(config_bytes)["config"])
    checked_source = source_identity(args.receiver_source, args.short_entry)
    result = {}
    for name in args.case or CASES:
        stock_root, short_root, archived = CASES[name]
        stock, stock_owners, stock_terminal = load(stock_root, STOCK)
        short, short_owners, short_terminal = load(short_root, SHORT)
        if archived is not None:
            stock_owners = original_owners(HERE / "measurements/track-quadrature.json.gz", archived, stock)
        audit = compare(stock, short, both_arms(stock_owners), both_arms(short_owners), config)
        arms_before, arms_after = stock_terminal["arms"], short_terminal["arms"]
        result[name] = dict(audit, stock_native=stock_terminal["native_sha256"],
                            short_native=short_terminal["native_sha256"], stock_arms=arms_before,
                            short_arms=arms_after, raw_authority=stock["source"]["raw_recording_authority_digest"],
                            pub_endpoint_separation_km={a: published_separation(arms_before[a], arms_after[a]) for a in ARMS})
    with args.output.open("x") as stream:
        print(json.dumps(dict(track_config_sha256=sha256(config_bytes).hexdigest(), cases=result,
                              receiver_sources=checked_source),
                         indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    main()
