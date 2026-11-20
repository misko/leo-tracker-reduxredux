"""Compose archived original GLRT timings with measured compact checkpoint costs."""

import csv
import gzip
import heapq
import json
from pathlib import Path

from .. import whole_iq
from . import short_compact
from .sequential_fix_trial import SCREEN

WORKERS = (1, 4, 8)


def service_metrics(row):
    service = row["service"]
    manager = service["systemd"]

    def numeric(key, divisor=1):
        value = manager.get(key)
        return int(value) / divisor if value and value.isdecimal() else None

    return dict(
        wall_s=service["service_wall_s"],
        cpu_s=numeric("CPUUsageNSec", 1e9),
        memory_peak_mib=numeric("MemoryPeak", 1024**2),
        swap_peak_bytes=numeric("MemorySwapPeak"),
        input_preparation_wall_s=row["input_preparation_wall_s"],
    )


def raw_inputs(spec, binding):
    folder = SCREEN / binding["folder"]
    checked = {
        name: whole_iq.checked(folder / name, digest) for name, digest in binding["files"].items()
    }
    source = whole_iq.read(checked["source-lock.json"])
    original = whole_iq.read(whole_iq.checked(Path(spec["native"]), spec["native_sha256"]))
    regenerated = json.loads(gzip.decompress(checked["native.json.gz"].read_bytes()))
    receipt = whole_iq.read(checked["audit.json"])["raw"]
    for key in ("clock_anchor", "delivery_clocks", "last_sample_counter"):
        if original[key] != regenerated[key]:
            raise ValueError(f"full raw replay changed the capture's {key}")
    if (
        source["original"]["native"]["sha256"] != spec["native_sha256"]
        or original["source"]["probes"] != regenerated["source"]["probes"]
        or original["provenance"]["excluded_windows"]
        != regenerated["provenance"]["excluded_windows"]
        or not receipt["completed"]
    ):
        raise ValueError("full raw replay differs from the complete checkpoint detector authority")
    intervals = short_compact.scopes(original)
    epoch = original["clock_anchor"]["before"]["monotonic_ns"]
    with checked["timing.csv"].open(newline="") as file:
        timings = list(csv.DictReader(file))
    raw = []
    for interval, timing in zip(intervals, timings, strict=True):
        _, _, delivery, _, excluded, visit = interval
        if int(timing["visit"]) != visit or timing["status"] != (
            "processed" if excluded is None else "invalid_capture"
        ):
            raise ValueError("full raw timing does not match the native validity ledger")
        raw.append(
            dict(
                visit=visit,
                arrival_s=(delivery["monotonic_ns"] - epoch) / 1e9,
                raw_cpu_s=float(timing["cpu_ms"]) / 1000,
                raw_wall_s=float(timing["wall_ms"]) / 1000,
                valid=excluded is None,
            )
        )
    return raw, dict(
        archived_wall_s=receipt["wall_s"],
        archived_total_worker_cpu_s=receipt["completed_worker_cpu_s"],
        archived_detector_cpu_s=receipt["total_measured_detector_cpu_s"],
        archived_raw_workers=len(receipt["workers"]),
        valid_visits=receipt["valid"],
        scheduled_visits=receipt["scheduled"],
    )


def queue(raw, workers, *, hold_from=None, resume_s=0.0):
    lanes = [0.0] * workers
    ledger = []
    for row in raw:
        ready = row["arrival_s"]
        if hold_from is not None and row["visit"] >= hold_from:
            ready = max(ready, resume_s)
        start = max(ready, heapq.heappop(lanes))
        finish = start + row["raw_wall_s"]
        heapq.heappush(lanes, finish)
        ledger.append((start, finish))
    return ledger


def timing(rows, released, raw=None):
    metrics = [service_metrics(r) for r in rows]
    wall = [m["wall_s"] + (m["input_preparation_wall_s"] or 0.0) for m in metrics]
    pure = [r["support"]["available_s"][-1] for r in rows]
    visits = [r["support"]["scheduled"] for r in rows]
    valid = [r["support"]["scheduled"] - r["support"]["invalid"] for r in rows]
    speculative_cpu = sum(m["cpu_s"] for m in metrics[:2])
    stock_cpu = metrics[-1]["cpu_s"]
    chosen_cpu = speculative_cpu + (0 if released else stock_cpu)

    def compute(ready):
        first = ready[0] + wall[0]
        decision = max(first, ready[1]) + wall[1]
        terminal = decision if released else max(decision, ready[-1]) + wall[-1]
        return first, decision, terminal

    _, stored_gate, stored_terminal = compute(pure)
    summary = dict(
        released_at_255=released,
        valid_visits=valid[-1],
        valid_tail_after_255=valid[-1] - valid[1],
        compact_speculative_cpu_s=speculative_cpu,
        compact_stock_cpu_s=stock_cpu,
        compact_policy_cpu_s=chosen_cpu,
        compact_policy_extra_cpu_s=chosen_cpu - stock_cpu,
        factors_only_gate_elapsed_s=stored_gate,
        factors_only_stock_elapsed_s=pure[-1] + wall[-1],
        factors_only_policy_elapsed_s=stored_terminal,
        full_service_input_preparation_wall_recorded=metrics[-1]["input_preparation_wall_s"]
        is not None,
    )
    if raw is None:
        return summary
    if len(raw) != visits[-1] or sum(row["valid"] for row in raw) != valid[-1]:
        raise ValueError("original raw timing is not complete")

    total_raw_cpu = sum(row["raw_cpu_s"] for row in raw)
    barrier_opportunity = sum(row["raw_cpu_s"] for row in raw[visits[1] :])
    scenarios = []
    for workers in WORKERS:
        eager = queue(raw, workers)
        ready = [
            max(acquired, max(end for _, end in eager[:count]))
            for acquired, count in zip(pure, visits, strict=True)
        ]
        first, gate, terminal = compute(ready)
        saved = sum(
            row["raw_cpu_s"]
            for row, (begin, _) in zip(raw, eager, strict=True)
            if released and begin >= gate
        )
        saved_valid = sum(
            row["valid"]
            for row, (begin, _) in zip(raw, eager, strict=True)
            if released and begin >= gate
        )
        barrier_saved = barrier_opportunity if released else 0.0
        barrier = queue(raw, workers, hold_from=visits[1], resume_s=gate)
        barrier_full = max(pure[-1], max(end for _, end in barrier))
        scenarios.append(
            dict(
                raw_workers=workers,
                model_raw_full_ready_s=ready[-1],
                model_raw_last_dispatch_s=eager[-1][0],
                model_210_finish_s=first,
                model_255_finish_s=gate,
                model_full_original_finish_s=ready[-1] + wall[-1],
                model_eager_policy_finish_s=terminal,
                model_barrier_policy_finish_s=gate
                if released
                else max(gate, barrier_full) + wall[-1],
                raw_cpu_saved_eager_s=saved,
                valid_visits_saved_eager=saved_valid,
                raw_cpu_saved_barrier_s=barrier_saved,
                total_cpu_saved_eager_s=saved + stock_cpu - chosen_cpu,
                total_cpu_saved_barrier_s=barrier_saved + stock_cpu - chosen_cpu,
            )
        )
    return dict(
        summary,
        raw_det_full_cpu_s=total_raw_cpu,
        raw_det_tail_opportunity_cpu_s=barrier_opportunity,
        scenarios=scenarios,
    )
