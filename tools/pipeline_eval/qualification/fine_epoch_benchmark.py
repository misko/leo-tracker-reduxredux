"""Benchmark exact same-epoch preparation and direct-recheck reuse."""

import argparse
import gzip
from collections import defaultdict
from contextlib import nullcontext
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

from ..__main__ import encoded, save_json, write
from ..variants import fine_epoch_reuse as reuse
from . import fine_epoch_trial as trial
from .capture_runtime import checked, read
from .full_v5_check import _sha

MODES = ("original", "aperture", "guard")
MODULE = "tools.pipeline_eval.qualification.fine_epoch_benchmark"


def freeze(work):
    paths = Path(__file__), Path(reuse.__file__), work / "input-lock.json"
    parent = read(paths[-1])
    cases = {}
    for name, cfg in parent["cases"].items():
        # Rank the existing unconditional held IDs with a second fixed key.
        visits = sorted(
            (r["visit"] for r in cfg["rows"] if r["cohort"] == trial.ONE),
            key=lambda v: trial.order(name, "timed", v),
        )[:5]
        stress = [r["visit"] for r in cfg["rows"] if r["cohort"] == trial.GUARD]
        previous = work / f"{name}-profile.json.gz"
        cases[name] = dict(held=sorted(visits), stress=stress, profile_sha256=_sha(previous))
    save_json(
        work / "timing-lock.json",
        dict(
            cases=cases,
            sources={str(p): _sha(p) for p in paths},
            repeats=trial.REPEATS,
            modes=MODES,
        ),
    )


def run_worker(work, name, cpu):
    lock = read(work / "timing-lock.json")
    for p, h in lock["sources"].items():
        checked(Path(p), h)
    acquisition, detector, cfg, policy, libs = trial.installed(work, name, cpu)
    binding = lock["cases"][name]
    measured = trial.prior.read_gzip(
        checked(work / f"{name}-profile.json.gz", binding["profile_sha256"])
    )
    if measured["case"] != name or measured["input_lock_sha256"] != _sha(work / "input-lock.json"):
        raise ValueError("benchmark could not authenticate traced reference candidates")
    original = {r["visit"]: r for r in measured["rows"]}
    grid = trial.PersistentGrid(libs["prepared"])

    def initialize(cls):
        wall, cpu0 = perf_counter_ns(), process_time_ns()
        obj = cls(libs["batch"], acquisition)
        if not obj.compatible:
            raise ValueError("the unchanged batch FFT sentinel failed")
        return obj, dict(
            cpu_ns=process_time_ns() - cpu0,
            wall_ns=perf_counter_ns() - wall,
            workspace_bytes=obj.workspace_bytes,
        )

    stock, a = initialize(trial.fine_batch.FineBatch)
    aperture, b = initialize(reuse.EpochBatch)
    evidence = []
    selected = set(binding["held"] + binding["stress"])
    try:
        with (
            trial.prior.exact.refiners(libs),
            grid.route(acquisition, trial.prior.capture_starts.screen_module()),
            patch.object(
                acquisition, "_retain_score_map_peaks", trial.prepared_hotpath_peaks.retained_peaks
            ),
        ):
            bank = acquisition._conditioned_frame_scores.__self__
            started = process_time_ns()
            guard = reuse.GuardReuse(acquisition, detector, grid, bank)
            guard_setup = process_time_ns() - started

            for index, (fixture, window) in enumerate(
                trial.prior.load_windows([row for row in cfg["rows"] if row["visit"] in selected])
            ):
                v = fixture["visit"]
                old = original[v]
                if old["iq_sha256"] != window.iq_sha256:
                    raise ValueError("benchmark wave disagrees with the profile IQ")
                wanted = encoded([old["public"], old["probes"]])
                modes = MODES if fixture["cohort"] == trial.ONE else ("original", "guard")
                clock = defaultdict(list)
                reason_ref = None
                for repeat in range(-1, trial.REPEATS):
                    turn = (index + repeat) % len(modes)
                    for order, mode in enumerate(modes[turn:] + modes[:turn]):
                        guard.hits.clear()
                        guard.retained_bytes = aperture.retained_bytes = aperture.hits = 0
                        grid.calls.clear()
                        start = len(bank.receipts)
                        engine = aperture.bind(detector) if mode == "aperture" else stock.route()
                        with engine, guard.route() if mode == "guard" else nullcontext():
                            observed, timing = trial.prior.prepared_hotpath_trial.sample(
                                window, policy
                            )
                        reasons = [x["fallback"] for x in bank.receipts[start:]]
                        if encoded(observed) != wanted or (
                            reason_ref is not None and reasons != reason_ref
                        ):
                            raise ValueError(
                                "cache changed a public field or conditioned guard decision"
                            )
                        reason_ref = reasons
                        clock[mode].append(
                            dict(
                                **timing,
                                repeat=repeat,
                                order=order,
                                grid_calls=len(grid.calls),
                                aperture_hits=aperture.hits,
                                cache_hits=dict(guard.hits),
                                retained_bytes=max(aperture.retained_bytes, guard.retained_bytes),
                                conditioned_searches=len(reasons),
                                direct_tie_scores=reasons.count("acquisition_rank_tie"),
                            )
                        )
                evidence.append(
                    dict(
                        visit=v,
                        cohort=fixture["cohort"],
                        iq_sha256=window.iq_sha256,
                        clocks=dict(clock),
                        reference_sha256=trial.sha256(wanted).hexdigest(),
                    )
                )
                print(name, v, fixture["cohort"], flush=True)
    finally:
        grid.clear_cache()
    data = dict(
        case=name,
        cpu=cpu,
        timing_lock_sha256=_sha(work / "timing-lock.json"),
        init=dict(original=a, aperture=b, guard_cpu_ns=guard_setup),
        peak_rss_kib=trial.prior.exact.stages.resident()["hwm_kib"],
        rows=evidence,
    )
    write(work / f"{name}-timing.json.gz", gzip.compress(encoded(data), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=Path)
    parser.add_argument("case", choices=trial.CASES, nargs="?")
    parser.add_argument("cpu", type=int, nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "run":
        trial.run(args.work, args.case, args.cpu, MODULE)
    else:
        run_worker(args.work, args.case, args.cpu)
