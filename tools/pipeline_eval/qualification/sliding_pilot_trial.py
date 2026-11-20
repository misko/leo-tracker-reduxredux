"""Evaluate rolling physical pilots on three original capture producers."""

import argparse
import gzip
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import fine_batch, prepared_hotpath_peaks, sliding_pilot
from ..variants.capture_fft import FullGrid
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import capture_exact_trial as exact
from . import fine_batch_trial as batch
from . import original_kernel_trial as original
from .capture_runtime import checked, read
from .coarse_basis_eval import captures, compare_map
from .full_v5_check import _load_case, _sha
from .prepared_hotpath_trial import sample

REPORT = ROOT / "reports/2026_11_19_receiver_screening/coarse-and-navigation/sliding-pilot-bank"
BATCH_QUALIFICATION = "b529eda1890f00ee6ecb7362de1fe2cd613888c8d8057224abb3c747d9aca1e9"
CASES = ("DS26-0237", "DS29-0082", "DS29-0519")
MODES = ("prepared", "rolling64", "rolling32", "paired32")
REPEATS = 5


def choose(name, visits, excluded):
    return sorted(
        (v for v in visits if 54 <= v <= 120 and v not in excluded),
        key=lambda v: sha256(encoded([name, "sliding-pilot-bank-blind-v1", v])).digest(),
    )[:2]


def freeze(work):
    work.mkdir()
    seal = checked(batch.REPORT / "qualification-lock.json", BATCH_QUALIFICATION)
    old = checked(batch.REPORT / "input-lock.json", read(seal)["files"]["input-lock.json"])
    lock = read(old)
    lock["cases"] = {name: lock["cases"][name] for name in CASES}
    for name, item in lock["cases"].items():
        case = _load_case(name)
        path, digest = exact.lineage.locked_native(case, "capture")
        probes = dict(
            visit_pairs(read(checked(path, digest.removeprefix("sha256:")))["source"]["probes"])
        )
        held = choose(name, probes.keys(), {r["visit"] for r in item["rows"]})
        development = next(v for v in range(37, 42) if v in probes)
        item["rows"] = []
        item["cpu"] = 4
        for visit, role in ((development, "development"), *((v, "blind") for v in held)):
            segment, manifest, window = original.decode(case, visit)
            archived = list(probes[visit])
            if any(
                p["valid_start_counter"] != window.acquisition["sample_start"] for p in archived
            ):
                raise ValueError("IQ and archived factor clocks disagree")
            item["rows"].append(
                dict(
                    visit=visit,
                    role=role,
                    segment=segment,
                    manifest=manifest,
                    iq_sha256=window.iq_sha256,
                    probes=archived,
                )
            )
        print(name, held, flush=True)
    library, command = sliding_pilot.build(work)
    lock["libs"]["sliding"] = dict(path=str(library), sha256=_sha(library))
    paths = (
        Path(__file__),
        Path(sliding_pilot.__file__),
        sliding_pilot.SOURCE,
        REPORT / "PROTOCOL.md",
        seal,
        old,
    )
    lock["sources"].update({str(path): _sha(path) for path in paths})
    lock.update(sliding_build=command, repeats=REPEATS, modes=MODES)
    save_json(work / "input-lock.json", lock)


class RetryOnly(FullGrid):
    def __init__(self, grid, retry):
        self.grid, self.retry = grid, retry
        self.calls = []

    def score_grid(self, acquisition, original, *args):
        target = self.retry if args[4] == sliding_pilot.RETRY else self.grid
        result = target.score_grid(acquisition, original, *args)
        self.calls.append(
            dict(target.calls[-1], selected="rolling" if target is self.retry else "fft")
        )
        return result


def development(window, policy, grids, acquisition):
    stock, _, inputs = captures(window, policy)
    rank = prepared_hotpath_peaks.retained_peaks
    rows = []
    for receiver, (args, ranking) in enumerate(inputs):
        for anchors in (args[4], sliding_pilot.RETRY):
            full_args = (*args[:4], anchors, args[-1])
            outputs, times = {}, []
            for mode in MODES:
                grids[mode].score_grid(acquisition, stock, *full_args)
            for rep in range(REPEATS):
                rotated = rep % len(MODES)
                order = MODES[rotated:] + MODES[:rotated]
                for mode in order:
                    start, wall = process_time_ns(), perf_counter_ns()
                    output = grids[mode].score_grid(acquisition, stock, *full_args)
                    cpu_ns, wall_ns = process_time_ns() - start, perf_counter_ns() - wall
                    row = grids[mode].calls[-1]
                    if not row["applied"]:
                        raise ValueError(f"unsupported genuine geometry: {row}")
                    times.append(
                        dict(
                            mode=mode,
                            cpu_ns=cpu_ns,
                            wall_ns=wall_ns,
                            repetition=rep,
                            first=order[0] == mode,
                            kernel=row,
                        )
                    )
                    outputs[mode] = np.asarray(output)
            baseline = outputs.pop("prepared")
            rows.append(
                dict(
                    receiver=receiver,
                    anchors=len(anchors),
                    timings=times,
                    comparisons={
                        mode: compare_map(baseline, output, rank, ranking)
                        for mode, output in outputs.items()
                    },
                    drift=sliding_pilot.drift(grids["rolling64"].library, args[0], args[3][0]),
                )
            )
    return rows


def held(window, policy, ports, fine, libs, acquisition):
    reference, _ = sample(window, policy)
    modes = tuple(ports)
    rows, outcomes = [], {}
    with (
        exact.refiners(libs),
        fine.route(),
        patch.object(acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks),
    ):
        for rep in range(-1, REPEATS):
            order = modes if rep % 2 == 0 else modes[::-1]
            for mode in order:
                grid = ports[mode]
                grid.calls.clear()
                with grid.route(acquisition, exact.starts.screen_module()):
                    observed, clock = sample(window, policy)
                if not grid.calls or not all(c["applied"] for c in grid.calls):
                    raise ValueError("held candidate lost physical coarse coverage")
                outcomes[mode] = observed
                number = sum(c["anchors"] == 22 for c in grid.calls)
                if rep >= 0:
                    rows.append(
                        dict(
                            clock,
                            mode=mode,
                            repetition=rep,
                            retries=number,
                            anchors=[c["anchors"] for c in grid.calls],
                            matches=observed == reference,
                            inverse_ffts=sum(c["inverse_ffts"] for c in grid.calls),
                        )
                    )
    return dict(
        status="matched" if all(r["matches"] for r in rows) else "different",
        public=reference[0],
        probes=reference[1],
        timings=rows,
        changed={mode: result for mode, result in outcomes.items() if result != reference},
    )


def worker(work, name):
    from leo.analysis.starlink import acquisition

    lockfile = work / "input-lock.json"
    lock = read(lockfile)
    cfg = lock["cases"][name]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("wrong worker CPU")
    checked(original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        checked(Path(path), digest)
    libs = {k: checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    case = _load_case(name)
    _, policy, evidence = exact.lineage.source_lineage(case)
    cap = evidence["capture"]
    if (cap["root"], cap["input_manifest_sha256"]) != (cfg["root"], cfg["input_manifest"]):
        raise ValueError("installed producer changed")
    fine = fine_batch.FineBatch(libs["batch"], acquisition)
    if not fine.compatible:
        raise ValueError("batched fine sentinel failed")
    prepared = PersistentGrid(libs["prepared"])
    grids = dict(
        prepared=prepared,
        rolling64=sliding_pilot.SlidingPilotGrid(libs["sliding"]),
        rolling32=sliding_pilot.SlidingPilotGrid(libs["sliding"], use_float=True),
        paired32=sliding_pilot.SlidingPilotGrid(libs["sliding"], use_float=True, use_pairs=True),
    )
    ports = dict(prepared=prepared, retry_only=RetryOnly(prepared, grids["paired32"]))
    records = []
    try:
        for item in cfg["rows"]:
            visit = item["visit"]
            segment, manifest, window = original.decode(case, visit)
            if (segment, manifest, window.iq_sha256) != (
                item["segment"],
                item["manifest"],
                item["iq_sha256"],
            ):
                raise ValueError("saved sample differs from frozen visit")
            if item["role"] == "development":
                data = dict(grids=development(window, policy, grids, acquisition))
            else:
                data = held(window, policy, ports, fine, libs, acquisition)
                if data["probes"] != item["probes"]:
                    raise ValueError("original detector does not reproduce archived probe payload")
            records.append(dict(visit=visit, role=item["role"], **data))
            print(name, visit, item["role"], data.get("status", "done"), flush=True)
    finally:
        prepared.clear_cache()
    save = dict(
        case=name,
        edge=cfg["edge"],
        peak_rss_kib=exact.stages.resident()["hwm_kib"],
        input_lock_sha256=_sha(lockfile),
        rows=records,
    )
    write(work / f"{name}.json.gz", gzip.compress(encoded(save), mtime=0))


def run(work):
    for name, cfg in read(work / "input-lock.json")["cases"].items():
        env = os.environ | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        for backend in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[f"{backend}_NUM_THREADS"] = "1"
        cmd = [
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
        subprocess.run(cmd, cwd=ROOT, env=env, check=True, timeout=130)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("case", nargs="?", choices=CASES)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker":
        worker(args.work, args.case)
    else:
        run(args.work)
