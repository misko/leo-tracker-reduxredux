"""Repeat the combined FFT path with exact vectorized local-peak selection."""

import argparse
import gzip
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from ..__main__ import encoded, local_output, save_json, write
from ..variants import anchor_grid, capture_fft
from . import capture_exact_trial as base
from . import capture_runtime as auth
from .full_v5_check import _load_case, _sha

ORDER = ("heap", "vector")


def evaluate(window, policy, libraries, mode):
    from leo.analysis.starlink import acquisition

    original = acquisition._retain_score_map_peaks
    pick = anchor_grid.retained_peaks if mode == "vector" else original
    grid = capture_fft.FullGrid(libraries["batched32"])
    with base.refiners(libraries), patch.object(acquisition, "_retain_score_map_peaks", pick):
        return base.stages.detector(window, policy, grid)


def verify(lock_path):
    lock = auth.read(lock_path)
    for p, digest in lock["sources"].items():
        auth.checked(Path(p), digest)
    auth.checked(base.WORK / "source-lock.json", lock["base_sha256"])
    cfg = auth.read(base.WORK / "source-lock.json")
    for p, digest in cfg["sources"].items():
        auth.checked(Path(p), digest)
    return cfg


def worker(path, ident):
    cfg = verify(path)
    case_cfg = cfg["cases"][ident]
    if os.sched_getaffinity(0) != {case_cfg["cpu"]}:
        raise ValueError("the selector requires the same paired CPU")
    case = _load_case(ident)
    _, policy, producer = base.lineage.source_lineage(case)
    if producer["capture"]["root"] != case_cfg["root"]["producer"]:
        raise ValueError("installed capture producer changed")
    libs = {k: auth.checked(Path(x["path"]), x["sha256"]) for k, x in cfg["libraries"].items()}
    traces = []
    for row in case_cfg["rows"]:
        window = base.starts.hinted_glrt_trial.load_selected(case, row)
        for repeat in range(2):
            modes = ORDER if (row["visit"] + repeat) % 2 else ORDER[::-1]
            for mode in modes:
                output = evaluate(window, policy, libs, mode)
                traces.append(
                    dict(
                        id=ident,
                        visit=row["visit"],
                        repeat=repeat,
                        mode=mode,
                        iq_sha256=window.iq_sha256,
                        result=output,
                    )
                )
    write(
        path.parent / f"{ident}-selector.json.gz",
        gzip.compress(
            encoded(
                dict(
                    traces=traces,
                    source_sha256=_sha(path),
                    cpu=case_cfg["cpu"],
                )
            ),
            mtime=0,
        ),
    )


def freeze(path):
    base_lock = base.WORK / "source-lock.json"
    save_json(
        path,
        dict(
            cases=list(base.CASES),
            base_sha256=_sha(base_lock),
            methods=ORDER,
            sources={str(p): _sha(p) for p in (Path(__file__), Path(anchor_grid.__file__))},
        ),
    )


def run(path, ids):
    cfg = verify(path)
    for ident in ids:
        record = cfg["cases"][ident]
        python = auth.checked(Path(record["python"]), record["python_sha256"])
        env = os.environ | {"PYTHONPATH": f"{record['root']['producer']}:{base.ROOT}"}
        for name in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[name + "_NUM_THREADS"] = "1"
        command = [
            "taskset",
            "-c",
            str(record["cpu"]),
            str(python),
            "-m",
            __spec__.name,
            "worker",
            str(path),
            ident,
        ]
        subprocess.run(command, env=env, cwd=base.ROOT, timeout=30, check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "worker", "run"))
    p.add_argument("lock", type=local_output)
    p.add_argument("cases", nargs="*", choices=tuple(base.CASES))
    a = p.parse_args()
    if a.action == "freeze":
        freeze(a.lock)
    elif a.action == "worker":
        worker(a.lock, a.cases[0])
    else:
        run(a.lock, a.cases)
