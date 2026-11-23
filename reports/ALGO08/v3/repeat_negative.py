"""Bound a sparse raw repeat gate on one existing signed member."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from math import isfinite, nan
import os
from pathlib import Path
import resource
from statistics import mean, median
import subprocess
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from . import receiver_ceiling_0169 as prior
from .low_bit_pilot_screen import adc, carrier_wave
from .mixed_aperture_receiver import INSTALLED_SHA, PILOT_SHA, NativePath, StereoSchedule, verified
from .scout_readout_trial import check_machine, factor_bytes


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "repeat_negative.c"
PROTOCOL = HERE / "repeat-negative-protocol.md"
STAGED_ROOT = Path("/dev/shm/leo-receiver-ceiling-0169-results01")
SCOPE_SHA = "95a438f0904e4568b6f2a3618b7fbf691c29d0e2d352fd3727cc83d35b72aa9a"
REFERENCES = {
    "stock": "b1d8a32033373c5996217fe3a70e9e7fe5ae58ba3f75439052eacd2ff55cb453",
    "full-short": "2f9102ffead53766ccc71317243618ff415de7c537cd4bb81b7b8b57488eea13",
}
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
STOCK = Path("/opt/leo-algo08/algo08v3/payload/receiver.so")
SHORT = prior.ORIGINAL / "short-primary.so"
MODES = {"full": 20, "short_primary": 12}
REPEATS = 2


def seal(path, result):
    with path.open("x") as file:
        json.dump(result, file, sort_keys=True, allow_nan=False, indent=2)
        file.write("\n")


def clock():
    return process_time_ns(), perf_counter_ns()


def elapsed(begin):
    return [end-start for start, end in zip(begin, clock(), strict=True)]


def identity(path):
    return sha256(path.read_bytes()).hexdigest()


def bindings():
    return {path.name: identity(path) for path in (PROTOCOL, SOURCE, Path(__file__))}


def compile_kernel(binary):
    flags = ["-std=c11", "-O3", "-march=x86-64-v3", "-fPIC", "-shared", "-Wall", "-Wextra", "-Werror"]
    subprocess.run(["cc", *flags, SOURCE, "-o", binary], check=True, timeout=10)
    return dict(binary_sha256=identity(binary), flags=flags,
                compiler=subprocess.check_output(["cc", "--version"], text=True).splitlines()[0])


class Screen:
    def __init__(self, library):
        self.call = ct.CDLL(str(library)).repeat_negative_score
        self.call.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, ct.c_int]
        self.call.restype = ct.c_double

    def score(self, samples, lane, mode):
        if (samples.shape != (200_000, 2, 2) or samples.dtype != np.dtype("<i2")
                or not samples.flags.c_contiguous or mode not in MODES):
            return nan
        return self.call(samples.ctypes.data, len(samples), lane, MODES[mode])


def keep(anchor, score, threshold):
    return anchor or not isfinite(score) or score >= threshold


def load_paths(stack, edge):
    verified(STOCK, INSTALLED_SHA)
    verified(SHORT, prior.SHORT_SHA)
    body = verified(RELEASE / "assets" / f"{edge}.f32", PILOT_SHA[edge])
    asset = np.frombuffer(body, dtype="<f4")
    paths = {}
    for mode, path in (("full", STOCK), ("short_primary", SHORT)):
        native = NativePath(path, asset, mode)
        stack.callback(native.close)
        paths[mode] = native
    return asset, paths


def synthetic(asset):
    rng = np.random.default_rng(17_620_036)
    length = 200_000
    tones = [(10993, -639701), (27113, 554913)]
    pilots = [carrier_wave(asset, epoch, hz, rolled=False) for epoch, hz in tones]
    cases = [("noise", 0., 0, 0), ("tone", 0., 0, 0), ("weak-whole", .50, 0, length),
             ("strong-whole", 1., 0, length), ("early", .82, 0, 86_000),
             ("late", .82, 105_000, length)]
    for label, gain, start, stop in cases:
        samples = np.empty((length, 2, 2), dtype="<i2")
        for lane, pilot in enumerate(pilots):
            observed = (rng.normal(size=length) + 1j*rng.normal(size=length)) * (.39/np.sqrt(2))
            observed[start:stop] += gain * pilot[start:stop]
            if label == "tone":
                observed += np.exp(2j*np.pi*167_011*np.arange(length)/10_000_000)
            values = adc(1900 * observed)
            samples[:, lane, 0], samples[:, lane, 1] = values.real, values.imag
        yield label, samples


def calibrate(root):
    host = check_machine()
    root.mkdir()
    library = root / "repeat-negative.so"
    build = compile_kernel(library)
    screen = Screen(library)
    rows = []
    for edge in PILOT_SHA:
        with ExitStack() as stack:
            asset, paths = load_paths(stack, edge)
            center = 0 if edge == "lower" else 75_000
            for label, samples in synthetic(asset):
                digest = sha256(samples.tobytes()).hexdigest()
                for mode, path in paths.items():
                    for lane in (0, 1):
                        score = screen.score(samples, lane, mode)
                        factors, _ = path.run(samples, lane, center)
                        rows.append(dict(edge=edge, label=label, iq_sha256=digest, mode=mode, lane=lane,
                                         score=score, factors=factors))
    threshold = min(row["score"] for row in rows if row["factors"])
    seal(root / "calibration.json", dict(host=host, build=build, threshold=threshold, bindings=bindings(), rows=rows))


def held_input():
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import valid_window_support
    from leo.storage.fast_scan import FastSegmentSource
    from leo.storage.short_window import ShortWindowReader
    from tools.pipeline_eval.qualification.cache_residency import load_query
    from tools.pipeline_eval.variants.experimental.paired_sha256 import PairedSha256, paired_decoded_hashes

    clock_in = clock()
    blocks = resource.getrusage(resource.RUSAGE_SELF).ru_inblock
    scope = json.loads(verified(STAGED_ROOT / "scope.json", SCOPE_SHA))
    root = Path(scope["entry"]["path"])
    if root.resolve(strict=True) != root or root.parent != STAGED_ROOT:
        raise ValueError("Use only the existing staged signed member")
    source = FastSegmentSource(scope["entry"], stop_sequence=prior.WINDOWS)
    chunk = prior.first_member(source.reader.manifest)
    if chunk.model_dump(mode="json") != scope["member"] or tuple(source.receiver_ids) != (0, 1):
        raise ValueError("The staged member geometry differs")
    verified(prior.cold.CACHE_LIBRARY, prior.cold.CACHE_SHA)
    query = load_query(prior.cold.CACHE_LIBRARY)
    payload = root / chunk.payload_relative_path
    before = prior.snapshot(payload, chunk.compressed_bytes, query)
    if (before["observed_members"] != 1 or before["unavailable"]
            or before["cached_pages"] != before["observed_file_pages"]):
        raise ValueError("Staged payload is not fully resident")
    spec = json.loads(verified(prior.cold.PAYLOAD / "spec.json", prior.cold.SPEC_SHA))
    hasher = prior.cold.PAYLOAD / "paired-sha256.so"
    verified(hasher, spec["paired_sha256"]["sha256"])
    if not PairedSha256(hasher).hardware:
        raise ValueError("The staged comparison requires paired SHA-256")
    original = ShortWindowReader._member
    opened = []

    def member(reader, name, size, digest):
        if reader.path != root or name not in (chunk.index_relative_path, chunk.payload_relative_path):
            raise ValueError("Attempted a read outside the staged member")
        opened.append(name)
        return original(reader, name, size, digest)

    with patch.object(ShortWindowReader, "_member", member), paired_decoded_hashes(hasher):
        windows = list(source.windows())
    if opened != [chunk.index_relative_path, chunk.payload_relative_path] or len(windows) != prior.WINDOWS:
        raise ValueError("Expected one complete authenticated member traversal")
    policy = FastScanPolicyV2()
    accepted = [w for w in windows if valid_window_support(w.acquisition, w.sample_rate_hz,
                                                          w.samples.shape, source.receiver_ids, policy)]
    if len(accepted) != 51:
        raise ValueError("Admission changed relative to the signed control")
    return windows, accepted, dict(clock_ns=elapsed(clock_in), members=opened, residence=before,
                                    input_blocks=resource.getrusage(resource.RUSAGE_SELF).ru_inblock-blocks)


def load_reference(arm, windows):
    received = json.loads(verified(STAGED_ROOT / f"1-{arm}.json", REFERENCES[arm]))
    if [w.iq_sha256 for w in windows] != received["iq"]:
        raise ValueError("Held I/Q differs from the sealed signed reference")
    selection = {(p["visit_index"], p["receiver_id"]): prior.selected(p)
                 for p in received["packet"]["source"]["probes"]}
    trace = {(row["visit"], row["lane"]): row for row in received["trace"]}
    if list(trace) != list(selection):
        raise ValueError("Signed native and selected reference orders disagree")
    return trace, selection


def detector_row(path, screen, samples, lane, center, mode, anchor, threshold, gated):
    started = clock()
    score, gate_clock = None, [0, 0]
    if gated and not anchor:
        score = screen.score(samples, lane, mode)
        gate_clock = elapsed(started)
    skipped = score is not None and not keep(anchor, score, threshold)
    factors, native_clock = ((), [0, 0]) if skipped else path.run(samples, lane, center)
    return factors, dict(total=elapsed(started), native=native_clock, gate=gate_clock,
                         score=score if score is not None and isfinite(score) else None, skipped=skipped)


def paired_rows(windows, accepted, paths, screen, threshold, arm):
    reference, selection = load_reference(arm, windows)
    schedule = StereoSchedule(full_coverage=True)
    rows = []
    for w in accepted:
        a, target = w.acquisition, w.target
        visit, edge = a["global_visit"], target["edge"]
        center = target["rf_center_hz"] - target["lnb_lo_hz"] - a["actual_if_center_hz"]
        _, aperture = schedule.visit(edge, target, a)
        anchor = aperture == "full"
        mode = "full" if arm == "stock" else aperture
        for lane in (0, 1):
            key = (visit, lane)
            signed = reference[key]
            if signed["mode"] != mode:
                raise ValueError("Held plan differs from the matched signed reference")
            row = dict(visit=visit, lane=lane, channel=target["channel"], iq_sha256=w.iq_sha256,
                       anchor=anchor, mode=mode, signed=signed["factors"], selected=selection[key], repeats=[])
            for rep in range(REPEATS):
                clocks = {}
                order = ("gate", "direct") if (visit+lane+rep) % 2 else ("direct", "gate")
                for trial in order:
                    factors, clocks[trial] = detector_row(paths[mode], screen, w.samples, lane, center, mode,
                                                         anchor, threshold, trial == "gate")
                    expected = () if clocks[trial]["skipped"] else row["signed"]
                    if factor_bytes(factors) != factor_bytes(expected):
                        raise ValueError(f"Original signed output differs at {key}")
                row["repeats"].append(clocks)
            picks = [(trial["gate"]["score"], trial["gate"]["skipped"]) for trial in row["repeats"]]
            if any(pick != picks[0] for pick in picks[1:]):
                raise ValueError("Repeat gate decision is unstable")
            row["score"], row["skipped"] = picks[0]
            rows.append(row)
    if [(r["visit"], r["lane"]) for r in rows] != list(reference):
        raise ValueError("Held admission order differs from the original reference")
    return rows


def summarize(rows):
    exposed = [row for row in rows if not row["anchor"]]
    positives = [r for r in exposed if r["signed"]]
    empties = [r for r in exposed if not r["signed"]]
    misses = [r for r in positives if r["skipped"]]
    cutoff = min((r["score"] for r in positives if r["score"] is not None), default=None)
    hindsight = [r for r in empties if cutoff is not None and not keep(False, r["score"] if r["score"] is not None else nan, cutoff)]
    genuine_skips = [r for r in empties if r["skipped"]]

    def total(data, trial, phase):
        return [median(sum(r["repeats"][rep][trial][phase][unit] for r in data)
                       for rep in range(REPEATS)) for unit in (0, 1)]

    return dict(lanes=len(rows), anchor_lanes=len(rows)-len(exposed), exposed_positive=len(positives),
                exposed_empty=len(empties), good_skips=len(genuine_skips), missed_lanes=len(misses),
                signed_by_rank=dict(Counter(f[0] for row in rows for f in row["signed"])),
                missed_by_rank=dict(Counter(f[0] for row in misses for f in row["signed"])),
                missed_selected=sum(len(r["selected"]) for r in misses),
                full_recall_hindsight=dict(cutoff=cutoff, empty_skips=len(hindsight), native_ns=total(hindsight, "direct", "native")),
                actual_detector_ns=total(rows, "direct", "total"), routed_detector_ns=total(rows, "gate", "total"),
                good_avoided_native_ns=total(genuine_skips, "direct", "native"),
                perfect_empty_native_ns=total(empties, "direct", "native"),
                gate_ns=total(exposed, "gate", "gate"),
                mean_gate_ns=[mean(r["repeats"][rep]["gate"]["gate"][unit] for r in exposed for rep in range(REPEATS))
                              if exposed else 0 for unit in (0, 1)])


def validate(calibration, digest, output):
    host = check_machine()
    raw = json.loads(verified(calibration, digest))
    if raw["bindings"] != bindings() or raw["threshold"] != min(r["score"] for r in raw["rows"] if r["factors"]):
        raise ValueError("Calibration does not bind the exact frozen score and threshold")
    library = calibration.with_name("repeat-negative.so")
    verified(library, raw["build"]["binary_sha256"])
    screen = Screen(library)
    windows, accepted, intake = held_input()
    output.mkdir()
    with ExitStack() as stack:
        _, paths = load_paths(stack, "lower")
        results = {arm: paired_rows(windows, accepted, paths, screen, raw["threshold"], arm) for arm in REFERENCES}
    seal(output / "result.json", dict(host=host, calibration_sha256=digest, threshold=raw["threshold"],
         bindings=bindings(), source=REFERENCES, scope_sha256=SCOPE_SHA, intake=intake,
         arms={arm: dict(rows=rows, pooled=summarize(rows), radios={str(lane): summarize([r for r in rows if r["lane"] == lane])
                                                                   for lane in (0, 1)}) for arm, rows in results.items()}))


def tmpfs(path):
    if not path.is_absolute() or path.resolve() != path or not path.is_relative_to("/dev/shm"):
        raise argparse.ArgumentTypeError("Use a canonical path on tmpfs")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("calibrate", "validate"):
        sub = commands.add_parser(command)
        sub.add_argument("output", type=lambda arg: tmpfs(Path(arg)))
        if command == "validate":
            sub.add_argument("calibration", type=lambda arg: tmpfs(Path(arg)))
            sub.add_argument("sha256")
    args = parser.parse_args()
    if args.command == "calibrate":
        calibrate(args.output)
    else:
        validate(args.calibration, args.sha256, args.output)
