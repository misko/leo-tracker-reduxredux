"""Reserve new physical visits and compare quarter-rate acquisition on live and null samples."""

import argparse
import gzip
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from time import process_time

import numpy as np
from scipy import fft

from leo.analysis.starlink.templates import edge_frequencies_hz

from ..variants import frame_stack_pilot, quarter_rate_pilot
from ..variants.portable_field import Detector
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import CASES, REPORT, digest, packed, select
from .reverse_glrt_report import read
from .reverse_glrt_search import WORK, Verifier, key


def reserve(parent, out):
    manifest = read(parent / "manifest.json")
    src = parent / "opportunities.jsonl.gz"
    if _sha(src) != manifest["opportunities_sha256"]:
        raise ValueError("native ledger differs")
    used = set()
    previous = {}
    for sub in ("", "heldout", "replication", "recovery"):
        path = parent / sub / "roster.json"
        actual = _sha(path)
        if actual != read(path.parent / "manifest.json")["roster_sha256"]:
            raise ValueError("earlier roster differs")
        previous[sub or "initial"] = actual
        used.update((r["case"], r["visit"]) for r in read(path))
    pool = defaultdict(list)
    with gzip.open(src, "rt") as stream:
        for line in stream:
            r = json.loads(line)
            if (r["case"], r["visit"]) not in used:
                pool[r["case"]].append(r)
    raw = packed([r for case in CASES for r in select(pool[case])]) + b"\n"
    lock = dict(
        cases=manifest["cases"],
        roster_sha256=digest(raw),
        opportunities_sha256=manifest["opportunities_sha256"],
        excluded=previous,
        protocol_sha256=_sha(REPORT / "QUARTER-RATE.md"),
    )
    out.mkdir(exist_ok=True)
    for dest, value in [(out / "roster.json", raw), (out / "manifest.json", packed(lock) + b"\n")]:
        if dest.exists() and dest.read_bytes() != value:
            raise ValueError("fixed quarter-rate inputs changed")
        dest.write_bytes(value)
    print("reserved", len(json.loads(raw)), "new physical visits", flush=True)


def null_samples(raw, seed):
    rng = np.random.default_rng(seed)
    x = raw[:, :, 0] + 1j * raw[:, :, 1]
    phase = np.exp(2j * np.pi * rng.random(x.shape))
    z = fft.ifft(fft.fft(x, axis=0) * phase, axis=0)
    iq = np.stack([z.real, z.imag], axis=-1)
    return np.clip(np.rint(iq), -32768, 32767).astype("<i2")


def measure(job):
    r, out, work = job
    _, _, w = decode(_load_case(r["case"]), r["visit"])
    if w.acquisition["sample_start"] != r["counter"] or r["edge"] != w.target["edge"]:
        raise ValueError("wrong raw opportunity")
    rx = r["rx"]
    center = w.target["rf_center_hz"] - w.target["lnb_lo_hz"] - w.acquisition["actual_if_center_hz"]
    tones = edge_frequencies_hz(r["edge"])
    width = min(
        800000.0,
        w.sample_rate_hz / 2 + center + min(tones),
        w.sample_rate_hz / 2 - center - max(tones),
    )
    null = null_samples(w.samples, int(r["id"][-12:], 16))
    nullhash = "sha256:" + digest(null.tobytes())
    measurements = {}
    binary = work / "portable-field.so"
    with Detector(binary, r["edge"]) as original:
        for kind, window in (
            ("real", w),
            ("phase_null", replace(w, samples=null, iq_sha256=nullhash)),
        ):
            v = Verifier(binary, r["edge"], window.samples, rx)
            try:
                results = {}
                order = ["original", "stack", "quarter"]
                first = int(r["id"][-4:], 16) % 3
                for method in order[first:] + order[:first]:
                    start = process_time()
                    if method == "original":
                        values = original(window, window.receiver_ids)[rx].candidates
                        cost = sum(
                            (q["coarse_cpu_ns"] + q["verify_cpu_ns"]) * 1e-9
                            for q in original.attempts
                            if q["lane"] == rx
                        )
                        passes = [
                            p
                            for p in values
                            if p.fractional_margin is not None and p.fractional_margin >= 0.025
                        ]
                        p = max(
                            passes,
                            key=lambda a: (a.fractional_margin, -a.candidate_rank),
                            default=None,
                        )
                        winner = (
                            dict(
                                epoch=p.fractional_frame_phase_sample,
                                hz=p.fractional_tracking_cfo_hz,
                                margin=p.fractional_margin,
                            )
                            if p
                            else None
                        )
                    else:
                        raw = window.samples[:, rx]
                        samples = np.asarray(raw[:, 0] + 1j * raw[:, 1], np.complex64)
                        if v.lib.portable_verifier_load(v.ctx, window.samples.ctypes.data, rx):
                            raise ValueError("verifier rejected samples")
                        detector = quarter_rate_pilot if method == "quarter" else frame_stack_pilot
                        winner = detector.detect(
                            samples, r["edge"], center - width, center + width, v
                        )
                        cost = process_time() - start
                    results[method] = dict(winner=winner, cpu_s=cost)
                measurements[kind] = results
            finally:
                v.close()
    payload = dict(key=key(r), signed_iq=w.iq_sha256, null_iq=nullhash, methods=measurements)
    path = out / "quarter" / (key(r) + ".json")
    temp = path.with_suffix(".partial")
    temp.write_bytes(packed(payload) + b"\n")
    temp.replace(path)


def run(out, work, workers):
    roster = out / "roster.json"
    if _sha(roster) != read(out / "manifest.json")["roster_sha256"]:
        raise ValueError("held panel changed")
    dest = out / "quarter"
    dest.mkdir(exist_ok=True)
    seal = dict(
        roster=_sha(roster),
        kernel=_sha(Path(quarter_rate_pilot.__file__)),
        study=_sha(Path(__file__)),
        protocol=_sha(REPORT / "QUARTER-RATE.md"),
        binary=_sha(work / "portable-field.so"),
    )
    receipt = dest / "source-lock.json"
    if receipt.exists() and read(receipt) != seal and list(dest.glob("DS*.json")):
        raise ValueError("quarter-rate study changed")
    receipt.write_bytes(packed(seal) + b"\n")
    pending = [(r, out, work) for r in read(roster) if not (dest / (key(r) + ".json")).exists()]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        list(pool.map(measure, pending))
    print("real and matched phase-null comparisons", len(list(dest.glob("DS*.json"))), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--parent", type=Path, default=REPORT)
    p.add_argument("--report", type=Path, default=REPORT / "quarter-holdout")
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--workers", type=int, default=3)
    p.add_argument("--reserve", action="store_true")
    a = p.parse_args()
    if a.reserve:
        reserve(a.parent, a.report)
    else:
        run(a.report, a.work, a.workers)
