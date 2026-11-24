"""Test a three-origin negative screen without rerunning the native detector."""

import argparse
from collections import Counter
import ctypes
import gzip
from hashlib import sha256
import json
from math import ceil, isfinite, nan
import os
from pathlib import Path
import resource
from statistics import mean
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from . import four_frame_primary as previous
from .mixed_aperture_receiver import strongest
from .zstd_wide_huffman import BUNDLED_SHA, NAMES, READER_SHA, release, view_for


HERE = Path(__file__).resolve().parent
RECEIPTS = {
    "0008": "773d366dd41072b8b21fd5765955f1072d668e9d5f975c94cd2c118121743334",
    "0169": "ce47f0d99aade3226a5d320d1351c23b45d1b95a14e50cede2caf11a7becc08d",
}
PREFIX = 40_000
SPLIT = 32
INTAKE_PIN = "b6a9e50f5b3be9e4987e2bef3727931509a9a017ad4a3ae269d3eb390983c390"


def verified_receipt(name, pin):
    body = (HERE / "measurements" / name).read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Reference receipt changed: {name}")
    return json.loads(gzip.decompress(body))


def source_bindings():
    names = ("three_origin_negative.py", "three_origin_negative.c", "three-origin-negative-protocol.md")
    return {name: sha256((HERE / name).read_bytes()).hexdigest() for name in names}


def reference(case):
    docs = verified_receipt(f"four-frame-primary-{case}.json.gz", RECEIPTS[case])
    a, b = (pair["runs"]["eight"]["packet"] for pair in docs["comparisons"])
    if (a["probes"] != b["probes"] or a["acquisition"]["ordered_input_sha256"]
            != b["acquisition"]["ordered_input_sha256"]):
        raise ValueError("The two original 8 ms arms must agree")
    return docs, a


class Screen:
    def __init__(self, library, digest):
        release.verified(library, digest)
        self.call = ctypes.CDLL(str(library)).three_origin_score
        self.call.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.call.restype = ctypes.c_double

    def score(self, samples, lane):
        if (samples.ndim != 3 or samples.shape[0] < PREFIX or samples.shape[1:] != (2, 2)
                or samples.dtype != np.dtype("<i2") or not samples.flags.c_contiguous):
            return nan
        return self.call(samples.ctypes.data, PREFIX, lane)


def capture(case, library, digest):
    import zstandard.backend_c as cext

    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage import short_window
    from leo.storage.fast_scan import FastSegmentSource
    from tools.pipeline_eval.qualification.cache_residency import load_query

    machine = previous.check_machine()
    member, manifest, chunk = previous.first_member.assignment(case)
    if (member.resolve(strict=True) != member or not member.is_relative_to("/dev/shm")
            or member.stat().st_dev != Path("/dev/shm").stat().st_dev):
        raise ValueError("Only the enrolled resident first member is in scope")
    for path, pin in ((cext.__file__, BUNDLED_SHA), (short_window.__file__, READER_SHA),
                      (release.CACHE_LIBRARY, release.CACHE_SHA)):
        release.verified(Path(path), pin)
    query = load_query(release.CACHE_LIBRARY)
    screen = Screen(library, digest)
    docs, packet = reference(case)
    stock = packet["acquisition"]
    if stock["chunk"] != chunk or packet["manifest"] != manifest or stock["issued"] != 64:
        raise ValueError("Archived native control differs from the enrolled member")
    anchors = {(row["visit_index"], row["receiver_id"]) for row in previous.first_member.anchor_lanes(packet["probes"])}
    policy = FastScanPolicyV2()
    state_before, view = view_for(member, NAMES, query)
    if view is None or state_before["filesystem"] != "tmpfs":
        raise ValueError("Missing resident input, no waveform was read")
    observed, scores, rejected = [], [], []
    c0, w0, r0 = process_time_ns(), perf_counter_ns(), resource.getrusage(resource.RUSAGE_SELF)
    with patch.object(short_window.ScannerIqStore, "_read_regular", staticmethod(view.read)):
        source = FastSegmentSource({"path": str(member), "manifest_digest": manifest}, stop_sequence=64)
        if tuple(source.receiver_ids) != (0, 1) or source.reader.manifest.chunks[0].model_dump(mode="json") != chunk:
            raise ValueError("Unexpected first-member geometry")
        for window in source.windows():
            visit = window.acquisition["global_visit"]
            if visit != window.sequence or visit != len(observed) or window.sample_rate_hz != 10_000_000:
                raise ValueError("Expected consecutive native-rate opportunities")
            observed.append([visit, window.iq_sha256])
            if not valid_window_support(window.acquisition, window.sample_rate_hz, window.samples.shape,
                                        source.receiver_ids, policy):
                rejected.append(visit)
                continue
            for lane in source.receiver_ids:
                if (visit, lane) in anchors:
                    continue
                cpu, wall = process_time_ns(), perf_counter_ns()
                score = screen.score(window.samples, lane)
                cost_cpu, cost_wall = process_time_ns() - cpu, perf_counter_ns() - wall
                scores.append(dict(visit=visit, antenna=lane, score=score if isfinite(score) else None,
                                   cpu_ns=cost_cpu, wall_ns=cost_wall))
    r1 = resource.getrusage(resource.RUSAGE_SELF)
    clock = dict(cpu_ns=process_time_ns()-c0, wall_ns=perf_counter_ns()-w0,
                 input_blocks=r1.ru_inblock-r0.ru_inblock, major_faults=r1.ru_majflt-r0.ru_majflt)
    after, _ = view_for(member, NAMES, query)
    keys = [(row["visit_index"], row["receiver_id"]) for row in packet["probes"]]
    if (len(observed) != 64 or canonical_digest(observed) != stock["ordered_input_sha256"]
            or rejected != stock["exclusions"] or len(anchors) != 16 or len(view.files) != len(NAMES)
            or [(row["visit"], row["antenna"]) for row in scores] != [key for key in keys if key not in anchors]
            or len(scores) != stock["receiver"]["native_calls"]["short_primary"] or "stop" in after):
        raise ValueError("Authenticated intake or original two-scan schedule changed")
    return dict(references=RECEIPTS[case], sources=source_bindings(), case=case, machine=machine,
                binary_sha256=digest, input=str(member), manifest=manifest, clock=clock,
                residence_before=state_before, residence_after=after, window_digests=observed,
                rejected=rejected, anchors=sorted(anchors), rows=scores,
                original_8ms_sha256=stock["receiver"]["short_primary_sha256"], release=docs["full_reference_sha256"])


def label(case, feature):
    docs, packet = reference(case)
    control = {(row["visit_index"], row["receiver_id"]): row for row in packet["probes"]}
    full = {(row["visit_index"], row["receiver_id"]): row for row in docs["full_reference"]}
    for feature_row in feature["rows"]:
        key = (feature_row["visit"], feature_row["antenna"])
        row, full_row = control[key], full[key]
        previous.paired_row(row, full_row)
        positive, known = strongest(row["candidates"]), strongest(full_row["candidates"])
        yield dict(feature_row, positive=bool(positive), strong=bool(positive and positive["fractional_margin"] >= .10),
                   cfo_hz=positive["fractional_tracking_cfo_hz"] if positive else None,
                   margin=positive["fractional_margin"] if positive else None,
                   common_20ms=previous.hit(previous.error(known, positive)))


def floor(rows):
    return min((row["score"] for row in rows if row["positive"] and row["score"] is not None), default=0.)


def omit(row, threshold):
    cue = row["score"]
    return cue is not None and isfinite(cue) and cue < threshold


def summary(rows, threshold, mean_short_cpu_ns):
    seen = Counter()
    excluded = []
    for row in rows:
        seen.update(calls=1, positive=row["positive"], strong=row["strong"], common_20ms=row["common_20ms"],
                    indeterminate=row["score"] is None)
        if omit(row, threshold):
            seen.update(skipped=1, skipped_empty=not row["positive"], lost=row["positive"],
                        lost_strong=row["strong"], lost_common_20ms=row["common_20ms"])
            excluded.append([row["visit"], row["antenna"]])
    hindsight = floor(rows)
    cpu = sum(row["cpu_ns"] for row in rows)
    return dict(counts={k: seen[k] for k in ("calls", "positive", "strong", "common_20ms", "indeterminate", "skipped",
                                            "skipped_empty", "lost", "lost_strong", "lost_common_20ms")},
                threshold=threshold, excluded=excluded, feature_cpu_ns=cpu,
                feature_wall_ns=sum(row["wall_ns"] for row in rows),
                informative_hindsight_floor=hindsight,
                hindsight_empty=sum(omit(row, hindsight) for row in rows if not row["positive"]),
                projected_net_cpu_ns=round(seen["skipped_empty"]*mean_short_cpu_ns-cpu),
                hindsight_net_cpu_ns=round(sum(omit(row, hindsight) for row in rows)*mean_short_cpu_ns-cpu))


def score(dense, held):
    cases = {"0008": dense, "0169": held}
    if (any(cue["case"] != case or cue["sources"] != source_bindings() or cue["references"] != RECEIPTS[case]
            for case, cue in cases.items()) or dense["binary_sha256"] != held["binary_sha256"]):
        raise ValueError("Feature rows lack a common frozen build or source binding")
    dense_rows, held_rows = (list(label(case, cue)) for case, cue in cases.items())
    training = [row for row in dense_rows if row["visit"] < SPLIT]
    test = [row for row in dense_rows if row["visit"] >= SPLIT]
    threshold = floor(training)
    scopes = {"dense_training": ("0008", training), "dense_later": ("0008", test),
              "dense_total": ("0008", dense_rows), "independent": ("0169", held_rows)}
    summaries = {}
    for scope, (case, rows) in scopes.items():
        docs, _ = reference(case)
        eight = [row["runs"]["eight"]["packet"]["acquisition"]["receiver"] for row in docs["comparisons"]]
        mean_ns = mean(row["native_cpu_ns"]["short_primary"]/row["native_calls"]["short_primary"] for row in eight)
        observations = summary(rows, threshold, mean_ns)
        observations["observed_population_mean_8ms_native_cpu_ns"] = mean_ns
        observations["by_antenna"] = [summary([row for row in rows if row["antenna"] == lane], threshold, mean_ns)
                                      for lane in (0, 1)]
        summaries[scope] = observations
    dense_short = summaries["dense_total"]["observed_population_mean_8ms_native_cpu_ns"]
    budget = 77_442_779/283_100_000
    fresh = verified_receipt("original-dense-intake.json.gz", INTAKE_PIN)
    bound = dict(through_detection_target_s=budget,
                 fresh_first_use_inner_clock_s=[pair["first_use"]["inner_receiver"]["elapsed_s"] for pair in fresh["pairs"]])
    bound["gap_s"] = [seconds-budget for seconds in bound["fresh_first_use_inner_clock_s"]]
    gate_cpu = summaries["dense_total"]["feature_cpu_ns"]
    bound["required_safe_empty_lanes_at_observed_mean"] = [ceil((gap*1e9 + gate_cpu)/dense_short) for gap in bound["gap_s"]]
    scientific = all(summaries[scope]["counts"]["lost"] == 0 for scope in ("dense_later", "independent"))
    worth_timing = summaries["dense_total"]["projected_net_cpu_ns"]/1e9 >= max(bound["gap_s"])
    return dict(qualified=scientific and worth_timing, all_original_positives_retained=scientific,
                mean_cost_budget_met=worth_timing, summaries=summaries, dense_budget=bound,
                measurements=cases, labeled_rows={"0008": dense_rows, "0169": held_rows})


def write(path, document):
    with path.open("x") as out:
        json.dump(document, out, indent=2, sort_keys=True, allow_nan=False)
        out.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    capture_cli = sub.add_parser("capture")
    capture_cli.add_argument("case", choices=RECEIPTS)
    capture_cli.add_argument("library", type=Path)
    capture_cli.add_argument("library_sha256")
    capture_cli.add_argument("output", type=Path)
    score_cli = sub.add_parser("score")
    score_cli.add_argument("dense", type=Path)
    score_cli.add_argument("held", type=Path)
    score_cli.add_argument("output", type=Path)
    args = parser.parse_args()
    result = (capture(args.case, args.library, args.library_sha256) if args.mode == "capture" else
              score(json.loads(args.dense.read_bytes()), json.loads(args.held.read_bytes())))
    write(args.output, result)
