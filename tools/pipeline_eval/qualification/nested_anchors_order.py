"""Audit actual ordered coarse peak keys on both grids for every reused retry."""

import argparse
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, save_json
from ..variants import prepared_hotpath_peaks
from . import nested_anchors_trial as trial
from .capture_runtime import checked, read
from .full_v5_check import _load_case, _sha

MODULE = "tools.pipeline_eval.qualification.nested_anchors_order"


def worker(work, name, cpu):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_detector as detector

    lock = read(work / "input-lock.json")
    case = lock["cases"][name]
    path = work / f"{name}.json.gz"
    measured = trial.prior.read_gzip(path)
    if os.sched_getaffinity(0) != {cpu} or measured["input_lock_sha256"] != _sha(
        work / "input-lock.json"
    ):
        raise ValueError("peak audit lacks its physical worker or input scope")
    for source, digest in (lock["sources"] | case["producer"]["sources"]).items():
        checked(Path(source), digest)
    _, policy, _ = trial.prior.exact.lineage.source_lineage(_load_case(name))
    earlier = {r["visit"]: r for r in measured["rows"] if r["grids"]}
    fixtures = [r for r in case["rows"] if r["visit"] in earlier]
    libs = {k: checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    grid = trial.nested.NestedGrid(checked(Path(lock["nested"]["path"]), lock["nested"]["sha256"]))
    pending, selection = {}, []
    choose = prepared_hotpath_peaks.retained_peaks

    def audit(args, rows, _support):
        complete = super(trial.nested.NestedGrid, grid).score_grid(*args)
        pending[id(rows)] = complete

    def retain(freq, rows, *args):
        actual = choose(freq, rows, *args)
        full = pending.pop(id(rows), None)
        if full is not None:
            check = choose(freq, full, *args)
            selection.append(
                dict(reused=[item[1:] for item in actual], full=[item[1:] for item in check])
            )
        return actual

    results = []
    try:
        with (
            trial.prior.exact.refiners(libs),
            grid.route(acquisition, trial.prior.capture_starts.screen_module()),
            patch.object(acquisition, "_retain_score_map_peaks", retain),
        ):
            grid.audit = audit
            for fixture, window in trial.prior.load_windows(fixtures):
                v = fixture["visit"]
                selection.clear()
                observed, _ = trial.measure(grid, detector, window, policy, "reuse")
                if (
                    pending
                    or len(selection) != len(earlier[v]["grids"])
                    or observed["public"] != earlier[v]["evidence"]["reuse"]["public"]
                    or observed["probes"] != earlier[v]["evidence"]["reuse"]["probes"]
                    or window.iq_sha256 != earlier[v]["iq_sha256"]
                ):
                    raise ValueError("peak-order audit changed the archived same-visit replay")
                results.append(dict(visit=v, iq_sha256=window.iq_sha256, peaks=list(selection)))
    finally:
        grid.clear_cache()
    save_json(
        work / f"{name}-order.json",
        dict(
            case=name, waveform_sha256=_sha(path), rows=results, program_sha256=_sha(Path(__file__))
        ),
    )


def run(work, cpu):
    lock = read(work / "input-lock.json")
    for case in trial.CASES:
        root = lock["cases"][case]["producer"]["producer"]
        env = os.environ | {"PYTHONPATH": f"{root}:{ROOT}"}
        env.update({p + "_NUM_THREADS": "1" for p in ("OMP", "OPENBLAS", "MKL", "NUMEXPR", "BLIS")})
        subprocess.run(
            [
                "taskset",
                "-c",
                str(cpu),
                str(trial.prior.original.PYTHON),
                "-u",
                "-m",
                MODULE,
                "worker",
                str(work),
                str(cpu),
                case,
            ],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=120,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("worker", "run"))
    parser.add_argument("work", type=Path)
    parser.add_argument("cpu", type=int)
    parser.add_argument("case", choices=trial.CASES, nargs="?")
    args = parser.parse_args()
    if args.action == "run":
        run(args.work, args.cpu)
    else:
        worker(args.work, args.case, args.cpu)
