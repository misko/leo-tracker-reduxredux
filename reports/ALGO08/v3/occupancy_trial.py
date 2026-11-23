"""Assess a fixed blind occupancy screen against the released two-scan receiver."""

import argparse
from collections import Counter
from contextlib import ExitStack
import gzip
import json
import math
from pathlib import Path
from random import Random
from statistics import mean
from time import perf_counter_ns, process_time_ns

import numpy as np

from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest, read_archive
from tools.pipeline_eval.variants.experimental.receiver_brackets import read_physical
from tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound import V3_SHA

from .directed_verifier_trial import continuation
from .scout_readout_trial import PILOT_SHA, check_machine, factor_bytes


FEATURES = ("inverse_flatness", "spectral_peakiness", "frame_repetition")
SCOPE = ("dense-development", "dense-contiguous", "dense-later", "weak", "south")
SOUTH = "6bd1f26bfa0bedfcf3f100f8"
FFT_INDEX = np.arange(256)[None, :] + np.array([4261, 48457, 102161, 159613])[:, None]
HANN = np.hanning(256)
FRAME_INDEX = (np.arange(6)*40000 + 1)//3
TILE_INDEX = (FRAME_INDEX[:, None, None] + np.linspace(211, 12811, num=8, dtype=int)[None, :, None]
              + np.arange(96)[None, None, :])
FLOOR = 1e-12
LEDGER = Path(__file__).resolve().parent / "measurements/primary-schedule.json.gz"
LEDGER_SHA = "9080bb1d5bb69d2df770593bc1878e6f151d1ba0a7cbbe320e365177552b0556"
SEED = 5882


def assignments():
    rng = Random(SEED)
    dev = rng.randrange(2) * 64
    return dict(dense_development=dev, dense_held=64-dev, dense_later=rng.choice((512, 640, 768, 896)))


def complex_lane(samples, indices, lane):
    iq = samples[indices, lane]
    return iq[..., 0] + 1j * iq[..., 1]


def scores(samples, lane):
    segments = complex_lane(samples, FFT_INDEX, lane)
    segments -= segments.mean(axis=1, keepdims=True)
    powers = np.mean(abs(np.fft.fft(segments * HANN, axis=1)) ** 2, axis=0)
    normalized = powers / max(float(np.mean(powers)), FLOOR)
    flatness = -float(np.mean(np.log(np.maximum(normalized, FLOOR)))) if np.any(powers) else 0.
    peakiness = float(np.quantile(normalized, .95) / max(np.median(normalized), FLOOR))

    tiles = complex_lane(samples, TILE_INDEX, lane)
    tiles -= tiles.mean(axis=2, keepdims=True)
    left, right = tiles[::2], tiles[1::2]
    dot = np.sum(left.conj() * right, axis=2)
    numerator = abs(dot) ** 2
    denom = np.sum(abs(left) ** 2, axis=2) * np.sum(abs(right) ** 2, axis=2)
    repetition = float(np.max(np.median(numerator / np.maximum(denom, FLOOR), axis=0)))
    return dict(zip(FEATURES, (flatness, peakiness, repetition), strict=True))


def cutoff(rows, feature, recall):
    positive = sorted(row["scores"][feature] for row in rows if row["factors"])
    if not positive:
        return -math.inf
    return positive[len(positive)-math.ceil(recall*len(positive))]


def evaluate(rows, choices):
    counts = Counter(positive=0, empty=0, skipped=0, missed_lanes=0, missed_factors=0,
                     empty_skipped=0, donor_skipped=0, selected_lane_skipped=0)
    paid = screen = oracle = saved = 0
    for row, keep in zip(rows, choices, strict=True):
        native = row["native_cpu_ns"]
        present = bool(row["factors"])
        counts["positive" if present else "empty"] += 1
        paid += native
        screen += row["screen_cpu_ns"]
        oracle += native if not present else 0
        if not keep:
            counts["skipped"] += 1
            counts["empty_skipped"] += not present
            counts["missed_lanes"] += present
            counts["missed_factors"] += len(row["factors"])
            counts["donor_skipped"] += present and row["selected"] is None
            counts["selected_lane_skipped"] += row["selected"] is not None
            saved += native
    return dict(counts=dict(counts), native_cpu_ns=paid, screen_cpu_ns=screen,
                perfect_empty_cpu_saved_ns=oracle, gross_skipped_cpu_ns=saved, net_cpu_saved_ns=saved-screen)


def calibration(rows):
    possibilities = {}
    for feature in FEATURES:
        threshold = cutoff(rows, feature, 1.)
        predicted = [row["scores"][feature] >= threshold for row in rows]
        possibilities[feature] = dict(threshold=threshold, **evaluate(rows, predicted))
    best = max(FEATURES, key=lambda name: possibilities[name]["net_cpu_saved_ns"])
    return best, possibilities[best]["threshold"], possibilities


def scope_windows(segment, start, stop, case, stride):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource

    source = FastSegmentSource(segment, start_sequence=start, stop_sequence=stop)
    policy = FastScanPolicyV2()
    if source.receiver_ids != (0, 1):
        raise ValueError("Expected the installed stereo receiver lanes")
    for window in source.windows():
        if (window.sequence - start) % stride or not valid_window_support(
                window.acquisition, window.sample_rate_hz, window.samples.shape, source.receiver_ids, policy):
            continue
        visit = window.acquisition["global_visit"]
        yield dict(case=case, key=f"{case}:{visit}", edge=window.target["edge"], target=window.target,
                   acquisition=window.acquisition, sha256=window.iq_sha256, visit=visit), window.samples


def input_groups(args):
    from leo.storage.fast_scan import FastScanStore

    dense = list(read_physical(args.binding, args.bulk, 128))
    binding = json.loads(args.binding.read_bytes())["case"]["recording"]["segments"][1]
    later = dict(path=(args.bulk / binding["path"]).parent, manifest_digest="sha256:" + binding["sha256"])
    _, _, inventory = FastScanStore(args.public).inventory(args.public / SOUTH, verify_windows=False)
    south = inventory["segments"][0]
    cuts = assignments()
    start = cuts["dense_later"] - 512
    held = list(scope_windows(later, start, start+64, "DS30-0008", 4))
    if any(not cuts["dense_later"] <= row["visit"] < cuts["dense_later"]+64 for row, _ in held):
        raise ValueError("The requested later member does not have the frozen global visit range")
    return {
        "dense-development": [(row, iq) for row, iq in dense if visit_index(row)//64 == cuts["dense_development"]//64],
        "dense-contiguous": [(row, iq) for row, iq in dense if visit_index(row)//64 == cuts["dense_held"]//64],
        "dense-later": held,
        "weak": list(read_archive(args.weak, 18)),
        "south": list(scope_windows(south, 0, 48, SOUTH, 1)),
    }


def center(row):
    target = row["target"]
    return target["rf_center_hz"] - target["lnb_lo_hz"] - row["acquisition"]["actual_if_center_hz"]


def visit_index(row):
    return row.get("visit", row["acquisition"].get("global_visit"))


def emitted(folder, radio, samples):
    rows = []
    for row, iq in samples:
        current = radio[row["edge"]]
        for lane in (0, 1):
            seen, cpu, _ = current.timed(iq, lane, center(row))
            clocks, estimates = [], []
            for _ in range(3):
                started = process_time_ns()
                estimates.append(scores(iq, lane))
                clocks.append(process_time_ns() - started)
            if estimates.count(estimates[0]) != len(estimates) or not all(math.isfinite(v) for v in estimates[0].values()):
                raise ValueError("Signal features are unstable or nonfinite")
            rows.append(dict(cohort=folder, key=row["key"], lane=lane, sha256=row["sha256"],
                             visit=visit_index(row),
                             factors=seen, scores=estimates[0], native_cpu_ns=cpu,
                             screen_cpu_ns=round(mean(clocks)), selected=None))
    return rows


def charged_route(radio, iq, records, feature, threshold):
    history, original, tested = {}, [], []
    start, wall = process_time_ns(), perf_counter_ns()
    for i, (row, samples) in enumerate(iq):
        current = radio[row["edge"]]
        for lane in (0, 1):
            record = records[2*i + lane]
            actual = ()
            if feature is None or scores(samples, lane)[feature] >= threshold:
                actual = current.timed(samples, lane, center(row))[0]
                if factor_bytes(actual) != factor_bytes(record["factors"]):
                    raise ValueError("Paid route changed stock factors")
            original.append(record["selected"])
            tested.append(continuation(history, row, lane, actual))
    return dict(native_screen_and_continuation_cpu_ns=process_time_ns()-start,
                native_screen_and_continuation_wall_ns=perf_counter_ns()-wall,
                changes=sum(a != b for a, b in zip(original, tested, strict=True)),
                lost=sum(a is not None and b is None for a, b in zip(original, tested, strict=True)),
                gained=sum(a is None and b is not None for a, b in zip(original, tested, strict=True)))


def historical_oracle(original):
    content = LEDGER.read_bytes()
    if digest(content) != LEDGER_SHA:
        raise ValueError("Recorded installed-v3 ledger changed")
    saved = json.loads(gzip.decompress(content))
    rows = saved["costs_and_factors"]
    if len(rows) != len(original):
        raise ValueError("Expected the historical 128-visit stock ledger")
    for old, now in zip(rows, original, strict=True):
        expected = [(f["candidate_rank"], f["integer_epoch_sample"], f["fractional_epoch_offset_samples"],
                     f["fractional_tracking_cfo_hz"], f["fractional_exact_score"], f["fractional_control_score"])
                    for f in old["full"]]
        if factor_bytes(expected) != factor_bytes(now["factors"]) or old["metadata"]["receiver_id"] != now["lane"]:
            raise ValueError("Original dense census no longer matches its installed native ledger")
    empty_cpu = sum(row["native_cpu_ns"][2] for row in rows if not row["full"])
    total_cpu = sum(row["native_cpu_ns"][2] for row in rows)
    measured = [run["cpu_s"] for run in saved["paired"]["strict"] if run["arm"] == "stock"]
    return dict(source_sha256=LEDGER_SHA, original_native_cpu_ns=total_cpu, ideal_empty_cpu_saved_ns=empty_cpu,
                old_paired_complete_cpu_s=measured, estimated_complete_share_saved=empty_cpu/1e9/mean(measured))


def run(args):
    machine = check_machine()
    if digest(args.installed.read_bytes()) != V3_SHA:
        raise ValueError("Unexpected installed detector")
    groups = input_groups(args)
    records, summaries = {}, {}
    with ExitStack() as stack:
        radio = {}
        for edge, pin in PILOT_SHA.items():
            asset = (args.assets / f"{edge}.f32").read_bytes()
            if digest(asset) != pin:
                raise ValueError("Unexpected pilot asset")
            radio[edge] = Receiver(args.installed, np.frombuffer(asset, dtype="<f4"))
            stack.callback(radio[edge].close)
        development = emitted(SCOPE[0], radio, groups[SCOPE[0]])
        feature, threshold, candidates = calibration(development)
        for name in SCOPE:
            records[name] = development if name == SCOPE[0] else emitted(name, radio, groups[name])
        # The first two cohorts are one complete causal replay. The disjoint
        # later rows have no original history and do not count continuation.
        dense = sorted(records[SCOPE[0]] + records[SCOPE[1]], key=lambda row: (row["visit"], row["lane"]))
        dense_iq = sorted(groups[SCOPE[0]] + groups[SCOPE[1]], key=lambda item: visit_index(item[0]))
        for iq, rows in ((dense_iq, dense), (groups["weak"], records["weak"]), (groups["south"], records["south"])):
            histories = {}
            for i, (row, _) in enumerate(iq):
                for lane in (0, 1):
                    record = rows[2*i + lane]
                    record["selected"] = continuation(histories, row, lane, record["factors"])
        for name in (*SCOPE, "dense-full-prefix"):
            rows = dense if name == "dense-full-prefix" else records[name]
            route = evaluate(rows, [row["scores"][feature] >= threshold for row in rows])
            roc = {key: {str(recall): evaluate(rows, [row["scores"][key] >= cutoff(rows, key, recall)
                                                     for row in rows]) for recall in (1., .99, .95)}
                   for key in FEATURES}
            if name == "dense-later":
                for arm in [route, *(point for feature_rows in roc.values() for point in feature_rows.values())]:
                    arm["counts"]["donor_skipped"] = None
            summaries[name] = dict(calibrated=route, optimistic_roc=roc)
        for name, iq, rows in (("dense-full-prefix", dense_iq, dense),
                               ("weak", groups["weak"], records["weak"]),
                               ("south", groups["south"], records["south"])):
            runs = []
            for order in (("screen", "stock"), ("stock", "screen")):
                pair = {arm: charged_route(radio, iq, rows, feature if arm == "screen" else None, threshold)
                        for arm in order}
                if pair["stock"]["changes"]:
                    raise ValueError("Stock causal replay changed its original selections")
                runs.append(pair)
            summaries[name]["route_replay"] = runs
    return dict(machine=machine, installed_sha256=V3_SHA, protocol_sha256=digest(
        Path(__file__).with_name("occupancy-protocol.md").read_bytes()),
        split=dict(seed=SEED, **assignments()),
        calibration=dict(feature=feature, threshold=threshold, candidates=candidates), records=records,
        summaries=summaries, historical_dense_oracle=historical_oracle(dense))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    for key in ("installed", "assets", "weak", "binding", "bulk", "public"):
        cli.add_argument(key, type=lambda value: Path(value).resolve())
    print(json.dumps(run(cli.parse_args()), indent=2, allow_nan=False))
