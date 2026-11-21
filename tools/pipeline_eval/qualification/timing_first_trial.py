"""Run original, timing-first capture and physical-band receivers on paired live and null inputs."""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from time import perf_counter, process_time

import numpy as np

from leo.analysis.starlink.templates import edge_frequencies_hz

from ..variants import delay_product_acquisition as receiver
from ..variants import delay_product_native as native
from ..variants.portable_field import Detector
from .full_v5_check import _load_case, _sha
from .original_kernel_trial import decode
from .reverse_glrt_reference import REPORT, digest, packed
from .reverse_glrt_report import read
from .reverse_glrt_search import WORK, key
from .reverse_quarter_trial import null_samples
from .timing_first_roster import OUT
from .timing_first_wide_reference import physical_bounds

SCRATCH = Path("/srv/bulk/leo-dev/ds26-timing-first-20261120")


def inventories(out):
    return dict(
        development=REPORT,
        heldout=REPORT / "heldout",
        replication=REPORT / "replication",
        quarter_holdout=REPORT / "quarter-holdout",
        recovery=REPORT / "recovery",
        fresh_ds26=out / "fresh-ds26",
        fresh_ds29=out / "fresh-ds29",
    )


def original_trial(original, window):
    start, wall = process_time(), perf_counter()
    answer = original(window, window.receiver_ids)
    total, elapsed = process_time() - start, perf_counter() - wall
    lanes = []
    for idx, value in enumerate(answer):
        passed = [
            p
            for p in value.candidates
            if p.fractional_margin is not None and p.fractional_margin >= 0.025
        ]
        p = max(passed, key=lambda v: (v.fractional_margin, -v.candidate_rank), default=None)
        costs = [e for e in original.attempts if e["lane"] == idx]
        lanes.append(
            dict(
                winner=dict(
                    epoch=p.fractional_frame_phase_sample,
                    hz=p.fractional_tracking_cfo_hz,
                    margin=p.fractional_margin,
                )
                if p
                else None,
                cpu_s=sum((e["coarse_cpu_ns"] + e["verify_cpu_ns"]) * 1e-9 for e in costs),
                wall_s=sum((e["coarse_wall_ns"] + e["verify_wall_ns"]) * 1e-9 for e in costs),
            )
        )
    return dict(cpu_s=total, wall_s=elapsed, lanes=lanes)


def new_trial(kernel, window, bounds):
    start, wall = process_time(), perf_counter()
    lanes = []
    for idx in window.receiver_ids:
        one, t = process_time(), perf_counter()
        iq = window.samples[:, idx]
        samples = np.empty(len(iq), np.complex64)
        samples.real = iq[:, 0]
        samples.imag = iq[:, 1]
        win = receiver.detect(samples, window.target["edge"], *bounds, native=kernel)
        lanes.append(dict(winner=win, cpu_s=process_time() - one, wall_s=perf_counter() - t))
    return dict(cpu_s=process_time() - start, wall_s=perf_counter() - wall, lanes=lanes)


def partition(job):
    chosen, cpu, out, binary, old_binary = job
    os.sched_setaffinity(0, {cpu})
    detectors = {}
    kernel = native.Kernel(binary)
    try:
        for edge in ("lower", "upper"):
            detectors[edge] = Detector(old_binary, edge)
            receiver.templates(edge, 4, True)
            receiver.templates(edge, 1, False)
        for row, cohort in chosen:
            name = key(row)
            dest = out / "receiver" / (name + ".json")
            if dest.exists():
                continue
            _, manifest, w = decode(_load_case(row["case"]), row["visit"])
            if not (
                w.acquisition["sample_start"] == row["counter"]
                and w.target["channel"] == row["channel"]
                and w.target["edge"] == row["edge"]
                and w.acquisition["complete"]
                and not w.acquisition["quality_flags"]
            ):
                raise ValueError("wrong raw sample window")
            mid = (
                w.target["rf_center_hz"]
                - w.target["lnb_lo_hz"]
                - w.acquisition["actual_if_center_hz"]
            )
            off = edge_frequencies_hz(row["edge"])
            half = min(
                800000.0,
                w.sample_rate_hz / 2 + mid + min(off),
                w.sample_rate_hz / 2 - mid - max(off),
            )
            normal = (mid - half, mid + half)
            wide = physical_bounds(w, row["edge"])
            null = null_samples(w.samples, int(row["id"][-12:], 16))
            checksum = "sha256:" + digest(null.tobytes())
            random = replace(w, samples=null, iq_sha256=checksum)
            all_results = {}
            for kind, window in (("real", w), ("null", random)):
                modes = ["original", "nominal", "physical"]
                first = int(row["id"][-4:], 16) % 3
                results = {}
                for mode in modes[first:] + modes[:first]:
                    if mode == "original":
                        results[mode] = original_trial(detectors[row["edge"]], window)
                    else:
                        results[mode] = new_trial(
                            kernel, window, normal if mode == "nominal" else wide
                        )
                all_results[kind] = results
            old = row["incumbent"]
            replay = all_results["real"]["original"]["lanes"][row["rx"]]["winner"]
            if (old is None) != (replay is None) or (
                old and abs(old["fractional_tracking_cfo_hz"] - replay["hz"]) > 1e-5
            ):
                raise ValueError("deployed gate or signed frequency differs from archive")
            payload = dict(
                key=name,
                id=row["id"],
                case=row["case"],
                visit=row["visit"],
                rx=row["rx"],
                cohort=cohort,
                selection=row.get("selection"),
                edge=row["edge"],
                counter=row["counter"],
                iq=w.iq_sha256,
                null_iq=checksum,
                manifest=manifest,
                cpu=cpu,
                bounds=dict(nominal=normal, physical=wide),
                methods=all_results,
            )
            tmp = dest.with_suffix(".partial")
            tmp.write_bytes(packed(payload) + b"\n")
            tmp.replace(dest)
    finally:
        for detector in detectors.values():
            detector.__exit__(None, None, None)
    print("completed paired worker", cpu, len(chosen), flush=True)


def run(out, work, old, cpus):
    if not cpus or len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose distinct available CPU cores")
    binary = native.compile_kernel(work)
    dest = out / "receiver"
    dest.mkdir(parents=True, exist_ok=True)
    rows = []
    signatures = {}
    for name, folder in inventories(out).items():
        path = folder / "roster.json"
        signatures[name] = _sha(path)
        if signatures[name] != read(folder / "manifest.json")["roster_sha256"]:
            raise ValueError("waveform roster changed")
        rows.extend((r, name) for r in read(path))
    if len(rows) != len({(r["case"], r["visit"]) for r, _ in rows}):
        raise ValueError("physical visit already included")
    inputs = [
        Path(receiver.__file__),
        Path(native.__file__),
        native.SOURCE,
        Path(__file__),
        Path(null_samples.__code__.co_filename),
        OUT / "PROTOCOL.md",
        OUT / "RECEIVER.md",
    ]
    lock = dict(
        inputs={p.name: _sha(p) for p in inputs},
        binary=_sha(binary),
        original=_sha(old / "portable-field.so"),
        rosters=signatures,
        cpus=cpus,
    )
    receipt = dest / "source-lock.json"
    if receipt.exists() and read(receipt) != lock:
        raise ValueError("frozen receiver or inputs changed")
    receipt.write_bytes(packed(lock) + b"\n")
    rows.sort(key=lambda v: digest(packed(["paired-run-order-v1", v[0]["id"]])))
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        list(
            pool.map(
                partition,
                [
                    (rows[i :: len(cpus)], cpu, out, binary, old / "portable-field.so")
                    for i, cpu in enumerate(cpus)
                ],
            )
        )
    print("verified original and new receiver on", len(rows), "pairs", flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--report", type=Path, default=OUT)
    p.add_argument("--work", type=Path, default=SCRATCH)
    p.add_argument("--original", type=Path, default=WORK)
    p.add_argument("--cpus", type=int, nargs="+", default=[0, 2, 4, 6])
    a = p.parse_args()
    run(a.report, a.work, a.original, a.cpus)
