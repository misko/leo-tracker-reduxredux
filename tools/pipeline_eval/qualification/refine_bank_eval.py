"""Qualify the fused post-coarse GLRT on the fixed two-recording visit panel."""

import argparse
import gzip
import json
import os
import tracemalloc
from dataclasses import replace
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from unittest.mock import patch

import numpy as np

from ..__main__ import THREAD_ENV, encoded, write
from ..variants import anchor_grid, pilot_kernel, refine_bank
from .full_v5_check import PRODUCERS, _bind_producer, _from_production, _load_case, _probe, _sha
from .pilot_kernel_eval import _digest, _windows
from .spectral_grid_eval import REPEATS, SCHEDULE, SEQUENCES, _positives, _synthetic
from .spectral_position import STAGE_ONLY

MODES = ("control", "refine_bank")
CASE_CPUS = dict(zip(PRODUCERS, (12, 13), strict=True))


def compare_candidates(control, trial):
    a, b = (result.model_dump(mode="json") for result in (control, trial))
    names = ("candidate_rank", "epoch_sample", "passed_margin_gate", "fractional_epoch_status")
    groups = dict(score=0.0, epoch=0.0, cfo=0.0)
    ranks, availability, same_structure = True, True, True
    if len(a["receivers"]) != len(b["receivers"]):
        same_structure = False
    for left, right in zip(a["receivers"], b["receivers"], strict=False):
        same_structure &= left["receiver_id"] == right["receiver_id"]
        same_structure &= len(left["candidates"]) == len(right["candidates"])
        for x, y in zip(left["candidates"], right["candidates"], strict=False):
            ranks &= all(x[name] == y[name] for name in names)
            for field, old in x.items():
                new = y[field]
                if old is None or new is None:
                    availability &= old is new
                elif field not in names:
                    group = "cfo" if "cfo" in field else "epoch" if "sample" in field else "score"
                    groups[group] = max(groups[group], abs(old - new))
    winners = _positives(control) == _positives(trial)
    return dict(
        exact_payload=a == b,
        exact_candidate_keys=same_structure and ranks and availability,
        exact_positive_winners=winners,
        max_delta=groups,
        within_tolerances=same_structure and ranks and availability
        and groups["score"] <= 1e-12 and groups["epoch"] <= 1e-12 and groups["cfo"] <= 1e-8,
    )


def _noise(window):
    rng = np.random.default_rng(745021)
    samples = np.rint(rng.normal(0, 500, window.samples.shape)).astype("<i2")
    return replace(window, samples=samples, iq_sha256=_digest(samples.tobytes()))


def _timed(window, call, index, repeats):
    outputs, timings = {}, {mode: [] for mode in MODES}
    stable = True
    for repeat in range(repeats):
        order = MODES if (index + repeat) % 2 == 0 else MODES[::-1]
        for mode in order:
            output, timing = call(window, mode)
            previous = outputs.setdefault(mode, output)
            stable &= previous == output
            timings[mode].append(timing)
    control, trial = (outputs[mode] for mode in MODES)
    comparison = compare_candidates(control, trial)
    probes = {mode: [_probe(window, r.receiver_id, map(_from_production, r.candidates))
                     for r in output.receivers] for mode, output in outputs.items()}
    payloads = {mode: _digest(encoded(output.model_dump(mode="json")))
                for mode, output in outputs.items()}
    return dict(
        sequence=window.sequence, visit=trial.visit, iq_sha256=window.iq_sha256,
        sample_start=trial.sample_start, sample_end=trial.sample_end,
        policy_status=trial.status, reason=trial.reason,
        equal_status=(control.status, control.reason) == (trial.status, trial.reason),
        stable=stable, production=probes["control"], native=probes["refine_bank"],
        comparison=comparison, payload_sha256=payloads, timings=timings,
        positive_winners={mode: _positives(result) for mode, result in outputs.items()},
    )


def summary(rows):
    valid = [row for row in rows if row["policy_status"] == "processed"]
    timing = {}
    for mode in MODES:
        by_visit = [row["timings"][mode] for row in valid]
        metrics = ("full_cpu_s", "full_wall_s", "integer_cpu_s", "fractional_cpu_s")
        timing[mode] = {
            "totals": {k: sum(r[k] for pair in by_visit for r in pair) for k in metrics},
            "visit_medians": {k: median(median(r[k] for r in pair) for pair in by_visit)
                              for k in metrics},
        }
    return dict(
        scheduled=len(rows), valid=len(valid), timing=timing,
        exact=all(row["comparison"]["exact_payload"] and row["stable"] for row in rows),
        original=all(row["matches_original_payload"] for row in rows),
    )


def replay(case_id, split, work):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_detector
    from leo.scanner.fast_scan_analysis import analyze_window

    policy = FastScanPolicyV2()
    case = _load_case(case_id)
    producer = _bind_producer(case, PRODUCERS[case_id], policy)
    prior_path = STAGE_ONLY / f"{case_id}-{split}.json.gz"
    prior = json.loads(gzip.decompress(prior_path.read_bytes()))
    segment = SCHEDULE[split]
    if (prior["producer"], prior["split"], prior["segment"]) != (producer, split, segment):
        raise ValueError("Historical detector receipt differs from the installed producer")
    tiled, library = work / "tiled.so", work / "refine-bank.so"
    pilot_kernel.compile_filter(tiled)
    refine_bank.compile_bank(library)
    coarse = anchor_grid.native_grid(tiled)
    bank = refine_bank.RefinementBank(library, fast_scan_scores)
    if not bank.compatible:
        raise ValueError("The new kernel did not match this NumPy reduction contract")
    original_refine = fast_scan_detector.refine_glrt64_epochs
    sampler = anchor_grid.fractional_sampler(fast_scan_scores.fractional_take)

    def call(window, mode):
        bank.reset()
        measures = dict(integer_cpu_s=0.0, fractional_cpu_s=0.0)
        integer = bank.integer if mode == "refine_bank" else bank.original_integer
        continuous = bank.fractional if mode == "refine_bank" else bank.original_fractional

        def clocked(label, function):
            def measure(*args, **kwargs):
                began = process_time()
                out = function(*args, **kwargs)
                measures[label + "_cpu_s"] += process_time() - began
                return out
            return measure

        integer_entry = clocked("integer", integer)
        refine_entry = clocked("fractional", original_refine)
        with (patch.object(acquisition, "_folded_anchor_score_grid", coarse),
              patch.object(acquisition, "_retain_score_map_peaks", anchor_grid.retained_peaks),
              patch.object(fast_scan_scores, "fractional_take", sampler),
              patch.object(fast_scan_detector, "conditioned_glrt64_scores", integer_entry),
              patch.object(fast_scan_detector, "refine_glrt64_epochs", refine_entry),
              patch.object(fast_scan_scores, "conditioned_glrt64_scores", integer),
              patch.object(fast_scan_scores, "conditioned_glrt64_score", continuous)):
            wall, cpu = perf_counter(), process_time()
            output = analyze_window(window, window.receiver_ids, None, policy)
            measures.update(full_cpu_s=process_time() - cpu, full_wall_s=perf_counter() - wall)
        return output, dict(measures, bank=bank.receipts)

    rows, memory, synthetic = [], {}, {}
    windows = _windows(case, segment, SEQUENCES)
    for window, before in zip(windows, prior["rows"], strict=True):
        row = _timed(window, call, len(rows), REPEATS)
        if any(row[k] != before[k] for k in ("sequence", "visit", "iq_sha256")):
            raise ValueError("Authenticated IQ visit changed from the fixed roster")
        row["matches_original_payload"] = all(
            sha == before["payload_sha256"]["installed"] for sha in row["payload_sha256"].values()
        )
        rows.append(row)
        print(case_id, split, row["visit"], row["policy_status"], row["comparison"], flush=True)
    if split == "development":
        first = next(window for window, row in zip(windows, rows, strict=True)
                     if row["policy_status"] == "processed")
        for mode in MODES:
            tracemalloc.start()
            call(first, mode)
            memory[mode] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        for name, (window, truth) in dict(_synthetic(first), noise=(_noise(first), None)).items():
            synthetic[name] = dict(_timed(window, call, 0, 1), truth=truth)
    sources = (Path(__file__), Path(refine_bank.__file__), refine_bank.SOURCE, pilot_kernel.SOURCE)
    return dict(
        case=case_id, split=split, segment=segment, producer=producer, rows=rows,
        summary=summary(rows),
        cpus=sorted(os.sched_getaffinity(0)), numpy=np.__version__, controls=synthetic,
        traced_peak_bytes=memory, source_sha256={source.name: _sha(source) for source in sources},
        library_sha256=_sha(library), original_detector_receipt_sha256=_sha(prior_path),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=PRODUCERS, required=True)
    parser.add_argument("--split", choices=SCHEDULE, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if os.sched_getaffinity(0) != {CASE_CPUS[args.case]} or any(
        os.environ.get(key) != "1" for key in THREAD_ENV
    ):
        parser.error("pin the designated CPU with one thread per numerical runtime")
    with TemporaryDirectory(prefix="refine-bank-") as work:
        result = replay(args.case, args.split, Path(work))
    write(args.out, gzip.compress(encoded(result) + b"\n", mtime=0))


if __name__ == "__main__":
    main()
