"""Compare two complete original capture paths on the frozen dual-window panel."""

import argparse
import gzip
import os
import subprocess
from contextlib import nullcontext
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import fine_search, prepared_hotpath_peaks
from ..variants.original_kernel import PersistentGrid
from . import original_kernel_trial as original
from . import prepared_hotpath_trial as previous
from .capture_runtime import checked, read
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/pilot-search-and-region/fine-search"
REPEATS = 5
MODES = ("row_wise", "pruned")


def freeze(work, cpu):
    work.mkdir()
    seal = previous.REPORT / "qualification-lock.json"
    receipt = read(seal)["files"]
    panel = checked(
        previous.REPORT / "selector-input-lock.json", receipt["selector-input-lock.json"]
    )
    lock = read(panel)
    runtime = original.PYTHON.parent.parent / "lib/python3.12/site-packages/numpy/fft"
    files = tuple(runtime.glob("_pocketfft_umath*.so"))
    if len(files) != 1:
        raise ValueError("capture interpreter must bind exactly one NumPy FFT runtime")
    paths = (
        Path(__file__),
        Path(fine_search.__file__),
        fine_search.SOURCE,
        Path(prepared_hotpath_peaks.__file__),
        REPORT / "PROTOCOL.md",
        seal,
        panel,
        *files,
    )
    lock["sources"].update({str(p): _sha(p) for p in paths})
    library, command = fine_search.build(work)
    lock["libs"]["fine"] = dict(path=str(library), sha256=_sha(library))
    for case in lock["cases"].values():
        case["cpu"] = cpu
    lock.update(modes=MODES, repeats=REPEATS, build=command)
    save_json(work / "input-lock.json", lock)


def audit(fine, function):
    rows = []

    def verify(values, template, rate, epoch, frequencies, symbols, *, transform_size):
        args = (values, template, rate, epoch, frequencies, symbols)
        start = process_time_ns()
        full = fine.original(*args, transform_size=transform_size)
        original_cpu_ns = process_time_ns() - start
        frames = fine.frames
        start = process_time_ns()
        prefix = fine.score(*args, transform_size=transform_size)
        pruned_cpu_ns = process_time_ns() - start
        if full != prefix:
            raise ValueError("pruned fine score tuple differs from the producer")
        top = sorted(full, reverse=True)[:2]
        rows.append(
            dict(
                epoch=int(epoch),
                first_cfo_hz=frequencies[0],
                last_cfo_hz=frequencies[-1],
                bins=len(full),
                frames=fine.frames - frames,
                best_minus_second=top[0] - top[1],
                original_cpu_ns=original_cpu_ns,
                pruned_cpu_ns=pruned_cpu_ns,
            )
        )
        return prefix

    with patch.object(fine.acquisition, "_normalized_frame_scores_fft", verify):
        result, _ = function()
    return result, rows


def worker(work, name):
    from leo.analysis.starlink import acquisition

    exact = previous.exact
    lockfile = work / "input-lock.json"
    lock = read(lockfile)
    cfg = lock["cases"][name]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("wrong pinned replay CPU")
    checked(original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        checked(Path(path), digest)
    libs = {
        name: checked(Path(info["path"]), info["sha256"]) for name, info in lock["libs"].items()
    }
    case = _load_case(name)
    _, policy, producer = exact.lineage.source_lineage(case)
    release = producer["capture"]
    if (release["root"], release["input_manifest_sha256"]) != (cfg["root"], cfg["input_manifest"]):
        raise ValueError("wrong installed capture release")
    grid = PersistentGrid(libs["prepared"])
    fine = fine_search.FineSearch(libs["fine"], acquisition)
    if not fine.compatible:
        raise ValueError("installed FFT runtime did not pass the arithmetic sentinel")
    modes = dict(row_wise=nullcontext, pruned=fine.route)
    records = []
    try:
        for index, fixture in enumerate(cfg["rows"]):
            visit = fixture["visit"]
            segment, manifest, window = original.decode(case, visit)
            if (segment, manifest, window.iq_sha256) != (
                fixture["segment"],
                fixture["manifest"],
                fixture["iq_sha256"],
            ):
                raise ValueError("resident IQ differs from frozen selection")
            stock, _ = previous.sample(window, policy)
            if stock[1] != fixture["probes"]:
                raise ValueError("installed producer changed the frozen factor archive")
            with (
                exact.refiners(libs),
                grid.route(acquisition, exact.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
            ):
                for route in modes.values():
                    with route():
                        observed, _ = previous.sample(window, policy)
                    if observed != stock:
                        raise ValueError(
                            f"{name}:{visit} warm call changed complete detector output"
                        )
                timings = []
                for rep in range(REPEATS):
                    order = MODES if (rep + index) % 2 == 0 else MODES[::-1]
                    for mode in order:
                        grid.calls.clear()
                        counts = (fine.calls, fine.fallbacks, fine.frames, fine.bins)
                        with modes[mode]():
                            observed, elapsed = previous.sample(window, policy)
                        full_grid = grid.calls and all(c["applied"] for c in grid.calls)
                        if observed != stock or not full_grid:
                            raise ValueError(
                                f"{name}:{visit} {mode} changed detector or coarse coverage"
                            )
                        fresh = (fine.calls, fine.fallbacks, fine.frames, fine.bins)
                        timings.append(
                            dict(
                                elapsed,
                                mode=mode,
                                repetition=rep,
                                first=mode == order[0],
                                fine=dict(
                                    zip(
                                        ("calls", "fallbacks", "frames", "bins"),
                                        (n - b for n, b in zip(fresh, counts, strict=True)),
                                        strict=True,
                                    )
                                ),
                                coarse_grids=len(grid.calls),
                            )
                        )
                observed, fine_rows = audit(
                    fine, lambda window=window: previous.sample(window, policy)
                )
            if observed != stock or not fine_rows or not all(row["frames"] for row in fine_rows):
                raise ValueError(f"{name}:{visit} fine audit changed detector support")
            records.append(
                dict(
                    visit=visit,
                    kind=fixture["kind"],
                    iq_sha256=window.iq_sha256,
                    public=stock[0],
                    probes=stock[1],
                    timings=timings,
                    fine_rows=fine_rows,
                )
            )
            print(
                name,
                visit,
                fixture["kind"],
                np.median([t["cpu_ns"] / 1e6 for t in timings if t["mode"] == "pruned"]),
                flush=True,
            )
    finally:
        grid.clear_cache()
    document = dict(
        case=name,
        cpu=cfg["cpu"],
        edge=cfg["edge"],
        root=cfg["root"],
        input_lock_sha256=_sha(lockfile),
        peak_rss_kib=exact.stages.resident()["hwm_kib"],
        workspace_bytes=fine.workspace_bytes,
        rotation_cache=fine_search._rotation.cache_info()._asdict(),
        rows=records,
    )
    write(work / f"{name}.json.gz", gzip.compress(encoded(document), mtime=0))


def run(work, names):
    lock = read(work / "input-lock.json")
    for name in names:
        cfg = lock["cases"][name]
        env = os.environ | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        for backend in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[f"{backend}_NUM_THREADS"] = "1"
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
    parser.add_argument("work", type=local_output)
    parser.add_argument("cases", nargs="*", choices=tuple(original.CASES))
    parser.add_argument("--cpu", type=int, default=1)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.cpu)
    elif args.action == "worker":
        worker(args.work, args.cases[0])
    else:
        run(args.work, args.cases or tuple(original.CASES))
