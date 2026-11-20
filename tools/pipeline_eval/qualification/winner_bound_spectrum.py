"""Time the late exact-score certificate on actual fractional correlation arrays."""

import argparse
import gzip
import os
import subprocess
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import winner_bound
from . import winner_bound_trial as trial
from .full_v5_check import _sha

REPEATS = 15
SIZE = 512


def component(values, grid):
    """Evaluate one branch with the producer's summation and FFT order."""
    count = values.shape[1]
    short_size = 1 << (2 * count - 2).bit_length()
    short = np.fft.fft(values, n=short_size, axis=1)
    autocorrelation = np.fft.ifft(np.sum(np.abs(short) ** 2, axis=0))
    packed = np.zeros(SIZE, dtype=np.complex128)
    packed[:count] = autocorrelation[:count]
    packed[-(count - 1) :] = autocorrelation[-(count - 1) :]
    spectrum = np.fft.fft(packed).real
    denom = winner_bound.ceiling(values)
    score = spectrum / denom if denom > 0 else spectrum
    best = int(np.argmax(score))
    return float(score[best]), float(grid[best])


def spectral_attempt(inputs, producer, paired, *, split, prune):
    """Return rank and score of the current valid winner and surviving score pairs."""
    maximum, evaluated = None, []
    for rank, exact, control in inputs:
        if split and exact.values.size and producer._uniform_glrt_geometry(exact, size=SIZE):
            producer._validate_glrt_pair(exact, control)
            grid = np.fft.fftfreq(SIZE, d=exact.symbol_step_s)
            exact_fit = component(exact.values, grid)
            if prune and winner_bound.can_skip(
                exact_fit[0], None if maximum is None else maximum[0]
            ):
                evaluated.append(None)
                continue
            result = exact_fit, component(control.values, grid)
        else:
            result = paired(exact, control, size=SIZE)
        evaluated.append(result)
        margin = result[0][0] - result[1][0]
        if margin >= winner_bound.GATE and (maximum is None or margin > maximum[0]):
            maximum = margin, rank, result[0][1]
    return maximum, evaluated


class Trace:
    def __init__(self, producer, refine):
        self.producer = producer
        self.original = refine
        self.timings = []
        self.attempts = []

    def refine(self, values, sample_rate, **geometry):
        scorer = self.producer.conditioned_glrt64_score
        paired = self.producer._glrt_pair
        correlations = []

        def terminal(samples, rate, **args):
            def capture(exact, control, *, size=SIZE):
                if size != SIZE:
                    raise ValueError("unexpected spectral grid")
                correlations.append((exact, control))
                return paired(exact, control, size=size)

            with patch.object(self.producer, "_glrt_pair", capture):
                return scorer(samples, rate, **args)

        with patch.object(self.producer, "conditioned_glrt64_score", terminal):
            result = self.original(values, sample_rate, **geometry)
        ranks = [i for i, row in enumerate(result) if row.fractional_margin is not None]
        self.attempts.append(ranks)
        inputs = [(rank, *basis) for rank, basis in zip(ranks, correlations, strict=True)]
        modes = {"paired": (False, False), "split_all": (True, False), "split": (True, True)}

        def evaluate(mode):
            split, prune = modes[mode]
            return spectral_attempt(inputs, self.producer, paired, split=split, prune=prune)

        check, stock = evaluate("paired")
        comparison, stopped = evaluate("split")
        if (
            evaluate("split_all") != (check, stock)
            or comparison != check
            or any(
                observed is not None and observed != reference
                for observed, reference in zip(stopped, stock, strict=True)
            )
        ):
            raise ValueError("split FFT changed surviving score or justifying winner")
        records = []
        sequence = list(modes)
        for repeat in range(REPEATS):
            measurements = {}
            start = (repeat + len(self.attempts)) % len(sequence)
            order = sequence[start:] + sequence[:start]
            if repeat % 2:
                order.reverse()
            for mode in order:
                start_wall, start_cpu = perf_counter_ns(), process_time_ns()
                outcome, _ = evaluate(mode)
                cpu, wall = process_time_ns() - start_cpu, perf_counter_ns() - start_wall
                if outcome != check:
                    raise ValueError("timed result changed the original winner")
                measurements[mode] = dict(cpu_ns=cpu, wall_ns=wall)
            records.append(measurements)
        self.timings.append(
            dict(
                rank_count=len(result),
                fractional_calls=len(inputs),
                skipped=stopped.count(None),
                winner=check,
                samples=records,
            )
        )
        return result


def worker(work, ident, cpu):
    source = trial.read(work / "input-lock.json")
    cfg = source["cases"][ident]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("wrong worker pin for paired local spectral timing")
    # Change only the pin in the checked original input after reading it.
    original_read = trial.read

    def source_read(path):
        fetched = original_read(path)
        if path == work / "input-lock.json":
            fetched["cases"][ident]["cpu"] = cpu
        return fetched

    visits = []

    class Collected(Trace):
        def __init__(self, producer, refine):
            super().__init__(producer, refine)
            visits.append(self.timings)

    with patch.multiple(trial, Audit=Collected, read=source_read):
        trial.worker(work, ident)
    output = [
        dict(visit=fixture["visit"], attempts=attempts)
        for fixture, attempts in zip(cfg["rows"], visits, strict=True)
    ]
    write(work / f"{ident}-spectra.json.gz", gzip.compress(encoded(output), mtime=0))


def run(original, work, cpu):
    path = trial.checked(original / "input-lock.json", _sha(trial.REPORT / "input-lock.json"))
    source = trial.read(path)
    work.mkdir()
    write(work / path.name, path.read_bytes())
    code_sha = _sha(Path(__file__))
    for ident, cfg in source["cases"].items():
        env = os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        subprocess.run(
            [
                "taskset",
                "-c",
                str(cpu),
                str(trial.prior.prior.original.PYTHON),
                "-Bu",
                "-m",
                __spec__.name,
                "worker",
                str(original),
                str(work),
                "--cpu",
                str(cpu),
                "--id",
                ident,
            ],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=100,
        )
        if _sha(Path(__file__)) != code_sha:
            raise ValueError("paired spectrum code changed during timing")
    outputs = tuple(work.glob("*-spectra.json.gz"))
    if len(outputs) != len(source["cases"]):
        raise ValueError("matched CPU timing did not cover the whole frozen sample")
    save_json(
        work / "spectrum-lock.json",
        dict(
            cpu=cpu,
            repeats=REPEATS,
            source_sha256=code_sha,
            input_lock_sha256=_sha(path),
            files={p.name: _sha(p) for p in outputs},
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("original", type=local_output)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--cpu", type=int, required=True)
    parser.add_argument("--id")
    args = parser.parse_args()
    if args.action == "run":
        run(args.original, args.work, args.cpu)
    else:
        worker(args.work, args.id, args.cpu)


if __name__ == "__main__":
    main()
