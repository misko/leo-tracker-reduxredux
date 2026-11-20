"""Isolate exact selector speed on the same frozen prepared capture panel."""

import argparse
import os
import subprocess
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

from ..__main__ import ROOT, save_json
from ..variants import anchor_grid, prepared_hotpath_peaks
from . import original_kernel_trial as original
from . import prepared_hotpath_trial as trial
from .capture_runtime import checked, read
from .full_v5_check import _sha

MODES = ("prepared", "vector", "lane")


def arm(mode, fine):
    if mode == "prepared":
        return nullcontext()
    choose = (
        anchor_grid.retained_peaks if mode == "vector" else prepared_hotpath_peaks.retained_peaks
    )
    return patch.object(fine.acquisition, "_retain_score_map_peaks", choose)


def freeze(work, predecessor):
    lock_path = predecessor / "input-lock.json"
    recorded = read(lock_path)
    for path, digest in recorded["sources"].items():
        checked(Path(path), digest)
    paths = (
        Path(__file__),
        Path(prepared_hotpath_peaks.__file__),
        trial.REPORT / "SELECTOR.md",
        lock_path,
    )
    recorded["sources"].update({str(path): _sha(path) for path in paths})
    recorded["modes"] = MODES
    save_json(work / "input-lock.json", recorded)


def run(work, cases):
    lock = read(work / "input-lock.json")
    for name in cases:
        cfg = lock["cases"][name]
        env = os.environ | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        for prefix in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[prefix + "_NUM_THREADS"] = "1"
        command = [
            "taskset",
            "-c",
            str(cfg["cpu"]),
            str(original.PYTHON),
            "-u",
            "-m",
            __spec__.name,
            "worker",
            str(work),
            name,
        ]
        subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=150)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("work", type=Path)
    parser.add_argument("cases", nargs="*", choices=tuple(original.CASES))
    parser.add_argument("--predecessor", type=Path)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.predecessor)
    elif args.action == "worker":
        with patch.multiple(trial, MODES=MODES, arm=arm, anchor_grid=prepared_hotpath_peaks):
            trial.worker(args.work, args.cases[0])
    else:
        run(args.work, args.cases)
