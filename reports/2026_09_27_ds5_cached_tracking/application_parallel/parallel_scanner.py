"""Research-only concurrent evaluation with the scanner's serial decision fold."""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from multiprocessing import get_context
from multiprocessing.shared_memory import SharedMemory

import numpy as np

from leo.scanner.detector import (
    DwellGlrt64Analysis,
    analyze_glrt64_dwell,
)
from leo.scanner.models import Glrt64FirstDetection, ScannerConfiguration


def _initialize(core_queue):
    os.sched_setaffinity(0, {core_queue.get(timeout=30)})


def evaluate_probe(task):
    name, shape, dtype, configuration, edge, column, receiver, index = task
    start = time.process_time_ns()
    shared = SharedMemory(name=name)
    try:
        values = np.ndarray(shape, dtype=np.dtype(dtype), buffer=shared.buf)
        values.flags.writeable = False
        begin = index * configuration.probe_stride_samples
        probe = np.ascontiguousarray(values[begin:begin + configuration.probe_samples, column], dtype=np.complex128)
        local = configuration.model_copy(update={"dwell_ms": 20, "receiver_ids": (receiver,)})
        result = analyze_glrt64_dwell(probe[:, None], local, edge=edge)
    finally:
        shared.close()
    response = replace(
        result.probes[0], probe_index=index,
        probe_start_ms=index * configuration.probe_stride_ms,
    )
    return response, (time.process_time_ns() - start) / 1e6


def fold_responses(responses, configuration):
    """Apply the unchanged history ordering after every complete two-RX probe."""
    responses = tuple(responses)
    expected = tuple(
        (index, receiver)
        for index in range(configuration.scheduled_probe_count)
        for receiver in configuration.receiver_ids
    )
    if tuple((row.probe_index, row.receiver_id) for row in responses) != expected:
        raise ValueError("parallel responses do not cover the ordered scanner schedule")
    history = {receiver: [] for receiver in configuration.receiver_ids}
    best = decision_best = first = None
    cursor = 0
    for _index in range(configuration.scheduled_probe_count):
        hits = []
        for _receiver in configuration.receiver_ids:
            probe = responses[cursor]
            cursor += 1
            for candidate in probe.candidates:
                best = candidate.margin if best is None else max(best, candidate.margin)
                if candidate.passed_margin_gate:
                    hits.append(Glrt64FirstDetection(
                        receiver_id=probe.receiver_id, probe_index=probe.probe_index,
                        probe_start_ms=probe.probe_start_ms,
                        candidate_rank=candidate.candidate_rank,
                        epoch_sample=candidate.epoch_sample,
                        acquired_cfo_hz=candidate.acquired_cfo_hz,
                        residual_cfo_hz=candidate.residual_cfo_hz,
                        tracking_cfo_hz=candidate.tracking_cfo_hz,
                        exact_score=candidate.exact_score,
                        control_score=candidate.control_score, margin=candidate.margin,
                    ))
        for hit in sorted(hits, key=lambda item: (item.receiver_id, -item.margin)):
            compatible = tuple(
                prior for prior in history[hit.receiver_id]
                if hit.probe_start_ms - prior.probe_start_ms >= configuration.probe_ms
                and abs(hit.tracking_cfo_hz - prior.tracking_cfo_hz) <= 8000.0
            )
            if compatible and first is None:
                first = min(compatible, key=lambda item: (item.probe_index, -item.margin))
                decision_best = best
        for hit in hits:
            history[hit.receiver_id].append(hit)
    if first is not None:
        return DwellGlrt64Analysis(
            first, decision_best, best,
            "two same-receiver non-overlapping 20 ms GLRT-64 probes "
            "passed the margin gate within 8 kHz CFO", responses,
        )
    return DwellGlrt64Analysis(
        None, best, best,
        f"all {configuration.scheduled_probe_count} overlapping "
        f"{configuration.probe_ms} ms probes completed without a confirmed "
        "same-receiver CFO-consistent pair", responses,
    )


class ParallelScanner:
    def __init__(self, cores):
        self.cores = tuple(cores)
        context = get_context("spawn")
        self.queue = context.Queue()
        for core in self.cores:
            self.queue.put(core)
        self.pool = ProcessPoolExecutor(
            max_workers=len(self.cores), mp_context=context,
            initializer=_initialize, initargs=(self.queue,),
        )

    def run(self, samples, configuration: ScannerConfiguration, *, edge):
        values = np.asarray(samples)
        expected = (configuration.dwell_samples, len(configuration.receiver_ids))
        if values.ndim != 2 or values.shape != expected:
            raise ValueError(f"scanner dwell has shape {values.shape}, expected {expected}")
        shared = SharedMemory(create=True, size=values.nbytes)
        try:
            np.ndarray(values.shape, dtype=values.dtype, buffer=shared.buf)[:] = values
            tasks = [
                (shared.name, values.shape, values.dtype.str, configuration, edge, column, receiver, index)
                for index in range(configuration.scheduled_probe_count)
                for column, receiver in enumerate(configuration.receiver_ids)
            ]
            evaluated = tuple(self.pool.map(evaluate_probe, tasks, chunksize=1))
        finally:
            shared.close()
            shared.unlink()
        return fold_responses((item[0] for item in evaluated), configuration), sum(
            item[1] for item in evaluated
        )

    def close(self):
        self.pool.shutdown(wait=True)
        self.queue.close()
        self.queue.join_thread()
