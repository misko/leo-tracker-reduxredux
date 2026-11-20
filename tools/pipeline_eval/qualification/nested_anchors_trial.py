"""Run three complete anchor schedules on frozen capture-era stereo IQ."""

import argparse
import gzip
import os
import subprocess
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import nested_anchors as nested
from ..variants import prepared_hotpath_peaks
from . import single_pass_trial as prior
from .capture_runtime import checked, read
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/coarse-and-navigation/nested-anchors"
WORK = Path("/srv/bulk/leo-dev/nested-anchors-20261120-A")
MODULE = "tools.pipeline_eval.qualification.nested_anchors_trial"
MODES = nested.MODES
REPEATS = 5
CASES = prior.CASE_IDS
HELD_N = 8


def freeze(work):
    parent = prior.sealed(prior.REPORT, "qualification-lock.json", "input-lock.json")
    lock = read(parent)
    work.mkdir()
    library, command = nested.build(work)
    for name in CASES:
        cfg = lock["cases"][name]
        choose = [r["visit"] for r in cfg["rows"] if r["cohort"] == prior.HELD][:HELD_N]
        cfg["rows"] = [r for r in cfg["rows"] if r["cohort"] == prior.KNOWN or r["visit"] in choose]
        print(name, choose, flush=True)
    paths = (
        Path(__file__),
        Path(nested.__file__),
        Path(prepared_hotpath_peaks.__file__),
        Path(prior.__file__),
        nested.capture_fft.SOURCE,
        nested.capture_fft.SOURCE.with_name("folded_bank.c"),
        nested.original_kernel.HEADER,
        work / "folded_bank.c",
        work / "capture_fft.c",
        parent,
        REPORT / "PROTOCOL.md",
    )
    lock.update(
        sources={str(p): _sha(p) for p in paths},
        nested=dict(path=str(library), sha256=_sha(library)),
        build=command,
        modes=MODES,
        repeats=REPEATS,
    )
    save_json(work / "input-lock.json", lock)


def measure(grid, detector, window, policy, mode):
    grid.calls.clear()
    with grid.window(detector, mode) as attempts:
        output, clocks = prior.prepared_hotpath_trial.sample(window, policy)
    prior.validate_attempts(attempts, "conditional", window.receiver_ids, output[1])
    if not all(x["applied"] for x in grid.calls):
        raise ValueError("resident IQ bypassed the prepared folded grid")

    def counts(count):
        return sum(c["anchors"] == count for c in grid.calls)

    retries = sum(n == 22 for _, n, _ in attempts)
    if mode == "reuse" and not retries <= grid.reuses <= 2 * retries:
        raise ValueError("nested retry did not reuse the actual failed receiver's primary grid")
    return dict(public=output[0], probes=output[1], attempts=attempts), dict(
        **clocks,
        grids={str(n): counts(n) for n in (10, 12, 22)},
        coarse_cpu_ns=sum(
            c["config_cpu_ns"] + c["native_cpu_ns"] + c.get("combine_cpu_ns", 0) for c in grid.calls
        ),
        inverse_ffts=sum(c["inverse_ffts"] for c in grid.calls),
        filter_ffts=sum(c["filter_ffts"] for c in grid.calls),
        reused_grids=grid.reuses,
        maximum_partial_bytes=grid.peak_partial_bytes,
        max_bank_bytes=max((c["buffer_bytes"] for c in grid.calls), default=0),
    )


def worker(work, name, cpu):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector as detector

    lock = read(work / "input-lock.json")
    cfg = lock["cases"][name]
    producer = cfg["producer"]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("worker outside its assigned CPU")
    checked(prior.original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | producer["sources"]).items():
        checked(Path(path), digest)
    capture, policy, seen = prior.exact.lineage.source_lineage(_load_case(name))
    if (capture["edge"], seen["capture"]["root"], seen["capture"]["input_manifest_sha256"]) != (
        producer["edge"],
        producer["producer"],
        producer["input_manifest_sha256"],
    ):
        raise ValueError("could not bind the original capture producer")
    libs = {k: checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    grid = nested.NestedGrid(checked(Path(lock["nested"]["path"]), lock["nested"]["sha256"]))
    records = []
    installed_cohorts = set()
    try:
        for i, (fixture, window) in enumerate(prior.load_windows(cfg["rows"])):
            stock = None
            if fixture["cohort"] not in installed_cohorts:
                stock, _ = prior.prepared_hotpath_trial.sample(window, policy)
                installed_cohorts.add(fixture["cohort"])
            grids = []

            def audit(args, combined, count, grids=grids):
                raw, support = grid._raw(*args)
                full = np.asarray(nested.divide(raw, support, out=raw))
                delta = full - np.asarray(combined)
                grids.append(
                    dict(
                        cells=delta.size,
                        differing=int(np.count_nonzero(delta)),
                        max_abs=float(np.max(np.abs(delta))),
                        rms=float(np.mean(delta * delta) ** 0.5),
                        support_equal=bool(np.array_equal(count, support)),
                    )
                )

            with (
                prior.exact.refiners(libs),
                grid.route(acquisition, prior.capture_starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
            ):

                def call(mode, window=window):
                    return measure(grid, detector, window, policy, mode)

                evidence, cold = {}, {}
                turn = i % len(MODES)
                for mode in MODES[turn:] + MODES[:turn]:
                    grid.clear_cache()
                    evidence[mode], cold[mode] = call(mode)
                if evidence["original"]["probes"] != fixture["probes"]:
                    raise ValueError("original archive did not reproduce on matching saved IQ")
                if (
                    stock is not None
                    and (evidence["original"]["public"], evidence["original"]["probes"]) != stock
                ):
                    raise ValueError(
                        "installed detector's full output changed in the normalized grid port"
                    )
                warm = defaultdict(list)
                if fixture["cohort"] == prior.HELD:
                    for mode in MODES:
                        call(mode)
                    for repeat in range(REPEATS):
                        turn = (i + repeat) % len(MODES)
                        for order, mode in enumerate(MODES[turn:] + MODES[:turn]):
                            result, timing = call(mode)
                            if result != evidence[mode]:
                                raise ValueError("a warm arm changed its full ordered payload")
                            warm[mode].append(dict(**timing, repeat=repeat, order=order))
                grid.audit = audit
                try:
                    output, _ = call("reuse")
                finally:
                    grid.audit = None
                if output != evidence["reuse"] or not all(g["support_equal"] for g in grids):
                    raise ValueError("grid instrumentation or integer support changed")
            records.append(
                dict(
                    visit=fixture["visit"],
                    iq_sha256=window.iq_sha256,
                    cohort=fixture["cohort"],
                    installed_checked=stock is not None,
                    evidence=evidence,
                    cold=cold,
                    warm=dict(warm),
                    grids=grids,
                )
            )
            print(
                name,
                fixture["visit"],
                len(evidence["recompute"]["attempts"]) - 2,
                evidence["recompute"] == evidence["reuse"],
                flush=True,
            )
    finally:
        grid.clear_cache()
    result = dict(
        case=name,
        cpu=cpu,
        rows=records,
        input_lock_sha256=_sha(work / "input-lock.json"),
        peak_rss_kib=prior.exact.stages.resident()["hwm_kib"],
    )
    write(work / f"{name}.json.gz", gzip.compress(encoded(result), mtime=0))


def run(work, name, cpu):
    producer = read(work / "input-lock.json")["cases"][name]["producer"]
    env = os.environ | {"PYTHONPATH": f"{producer['producer']}:{ROOT}"}
    for prefix in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
        env[prefix + "_NUM_THREADS"] = "1"
    subprocess.run(
        [
            "taskset",
            "-c",
            str(cpu),
            str(prior.original.PYTHON),
            "-u",
            "-m",
            MODULE,
            "worker",
            str(work),
            name,
            str(cpu),
        ],
        cwd=ROOT,
        env=env,
        check=True,
        timeout=260,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=Path, nargs="?", default=WORK)
    parser.add_argument("case", choices=CASES, nargs="?")
    parser.add_argument("cpu", type=int, nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    else:
        (run if args.action == "run" else worker)(args.work, args.case, args.cpu)
