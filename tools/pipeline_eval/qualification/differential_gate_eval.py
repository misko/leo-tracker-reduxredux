"""Audit the phase-consistent differential scout on authenticated raw IQ."""

import argparse
import gzip
import os
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, write
from ..variants import (
    anchor_grid,
    conditioned_cfo_bank,
    dense_q10,
    differential_gate,
    pilot_kernel,
    refine_bank,
    spectral_grid,
)
from . import dense_q10_eval, refine_bank_eval, sparse_epoch_eval, spectral_grid_eval
from .full_v5_check import PRODUCERS, _bind_producer, _load_case, _sha
from .pilot_kernel_eval import _digest, _windows

METHOD = "differential_gate"
CPUS = dict(zip(PRODUCERS, (1, 21), strict=True))
SCHEDULE = {"early": (6, (0, 2, 5, 7)), "late": (11, (0, 2, 5, 7))}
REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/pilot-acquisition"
LOCK = REPORT / "source-lock.json"


def frozen_sources():
    paths = (
        Path(__file__),
        Path(differential_gate.__file__),
        Path(refine_bank_eval.__file__),
        Path(sparse_epoch_eval.__file__),
        Path(spectral_grid_eval.__file__),
        REPORT / "PROTOCOL.md",
    )
    return dense_q10_eval.frozen_sources() | {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def _plant(window, signals, seed):
    from leo.analysis.starlink.templates import FRAME_RATE_HZ, qin_edge_pilot_frame

    rate = window.sample_rate_hz
    reference = qin_edge_pilot_frame(rate, window.target["edge"])
    center = (
        window.target["rf_center_hz"]
        - window.target["lnb_lo_hz"]
        - window.acquisition["actual_if_center_hz"]
    )
    indices = np.arange(len(reference))
    time = (np.arange(len(window.samples)) - len(window.samples) / 2) / rate
    signal = np.zeros(len(time), dtype=complex)
    for epoch, offset, cfo, strength, drift in signals:
        delay = indices - offset
        template = np.interp(delay, indices, reference.real, left=0, right=0)
        template = template + 1j * np.interp(delay, indices, reference.imag, left=0, right=0)
        component = np.zeros_like(signal)
        for frame in range(15):
            start = round(frame * rate / FRAME_RATE_HZ) + epoch
            length = min(len(template), len(signal) - start)
            component[start : start + length] = template[:length]
        phase = (center + cfo) * time + drift * time**2 / 2
        signal += strength * component * np.exp(2j * np.pi * phase)
    rng = np.random.default_rng(seed)
    iq = np.stack((signal.real, signal.imag), axis=-1)[:, None, :]
    samples = np.clip(np.rint(iq + rng.normal(0, 500, window.samples.shape)), -32768, 32767)
    samples = samples.astype("<i2")
    truth = [
        dict(epoch=e, offset=o, cfo=center + f, amplitude=a, drift_hz_s=d)
        for e, o, f, a, d in signals
    ]
    return replace(window, samples=samples, iq_sha256=_digest(samples.tobytes())), truth


def _timed(window, call, index, repeats):
    row = sparse_epoch_eval._timed(window, call, index, repeats)
    for key in ("timings", "payload_sha256", "payloads"):
        row[key][METHOD] = row[key].pop("sparse_epoch")
    return row


def replay(case_id, split, workspace, sources):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    case, policy = _load_case(case_id), FastScanPolicyV2()
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    segment, sequence = SCHEDULE[split]
    build = dict(
        tiled=pilot_kernel.compile_filter,
        spectral=spectral_grid.compile_filter,
        fused=refine_bank.compile_bank,
        cfo=conditioned_cfo_bank.compile_bank,
        baseline=dense_q10.compile_grid,
    )
    paths = {name: workspace / f"{name}.so" for name in build}
    for name, compile_library in build.items():
        compile_library(paths[name])
    tiled = anchor_grid.native_grid(paths["tiled"])
    grids = {
        "control": dense_q10.DenseQ10Grid(paths["baseline"], tiled),
        "sparse_epoch": differential_gate.DifferentialGate(paths["spectral"], tiled),
    }
    fused = refine_bank.RefinementBank(paths["fused"], fast_scan_scores)
    if not fused.compatible:
        raise ValueError("Fused refinement is incompatible with the original NumPy runtime")
    conditioner = conditioned_cfo_bank.ConditionedBank(paths["cfo"], acquisition)
    call = dense_q10_eval._paired_call(grids, fused, conditioner, policy)
    windows, rows = _windows(case, segment, sequence), []
    for index, window in enumerate(windows):
        row = _timed(window, call, index, 2)
        stock = analyze_window(window, window.receiver_ids, None, policy)
        digest = _digest(encoded(stock.model_dump(mode="json")))
        row["matches_original_control"] = row["payload_sha256"]["control"] == digest
        rows.append(row)
        print(
            case_id,
            split,
            row["visit"],
            row["exact_payload"],
            row["matches_original_control"],
            flush=True,
        )
    controls = {}
    if split == "early":
        first = next(
            w for w, row in zip(windows, rows, strict=True) if row["policy_status"] == "processed"
        )
        empty, _ = spectral_grid_eval._synthetic(first)["empty"]
        noise = refine_bank_eval._noise(first)
        examples = dict(empty=(empty, []), noise=(noise, []))
        plants = {
            "faint": ((735, 0, 48_000, 128, 0),),
            "off_phase_chirp": ((738, 0.4, -745_000, 192, 800_000),),
            "two_chirps": ((733, 0, -710_000, 1400, 600_000), (909, 0, 695_000, 850, -900_000)),
        }
        for i, (name, signals) in enumerate(plants.items()):
            examples[name] = _plant(first, signals, 830819 + i)
        for name, (window, truth) in examples.items():
            controls[name] = dict(_timed(window, call, 0, 1), truth=truth)
    return dict(
        case=case_id,
        split=split,
        segment=segment,
        producer=producer,
        rows=rows,
        controls=controls,
        source_sha256=sources,
        library_sha256={name: _sha(path) for name, path in paths.items()},
        cpus=sorted(os.sched_getaffinity(0)),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--split", choices=SCHEDULE, required=True)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {CPUS[args.case]} or any(
        os.environ.get(key) != "1" for key in THREAD_ENV
    ):
        parser.error("pin the designated CPU and all numerical threads")
    sources = frozen_sources()
    if LOCK.read_bytes() != encoded(sources) + b"\n":
        raise ValueError("The predeclared scout source lock no longer matches checkout")
    with TemporaryDirectory(prefix="differential-gate-") as work:
        result = replay(args.case, args.split, Path(work), sources)
    if frozen_sources() != sources:
        raise ValueError("The proposal source changed during the held replay")
    path = local_output(REPORT / f"{args.case}-{args.split}.json.gz")
    write(path, gzip.compress(encoded(result), mtime=0))


if __name__ == "__main__":
    main()
