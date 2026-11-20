"""Compare original public support and prepared fine FFT workspace on authentic CI16."""

import argparse
import gzip
import os
import subprocess
from collections import defaultdict
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import anchor_grid, prepared_hotpath
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from .capture_detector_replay import scan_capture_window
from .capture_runtime import checked, read
from .full_v5_check import _load_case, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/receiver-deadline/prepared-hotpath"
RUNS = 5
MODES = ("prepared", "fine", "fine_selector")
GATE = 0.025


def choose(name, probes, excluded):
    available = {v: rows for v, rows in visit_pairs(probes) if 32 <= v < 240 and v not in excluded}
    if not available:
        raise ValueError("no fresh paired calibration windows")

    def stable(visit):
        return sha256(encoded([name, "prepared-hotpath-v1", visit])).digest()

    choices = {}
    for count, kind in ((2, "dual-positive"), (1, "single-lane"), (0, "negative")):
        v = min(
            (
                v
                for v, rows in available.items()
                if sum(
                    any(c["passed_fractional_margin_gate"] for c in p["candidates"]) for p in rows
                )
                == count
            ),
            key=stable,
        )
        choices[kind] = (v, available.pop(v))

    def gate_gap(v):
        return min(
            (
                abs(c["fractional_margin"] - GATE)
                for p in available[v]
                for c in p["candidates"]
                if c["fractional_margin"] is not None
            ),
            default=float("inf"),
        )

    v = min(available, key=lambda v: (gate_gap(v), stable(v)))
    choices["near-gate"] = (v, available[v])
    return choices


def freeze(work):
    prior_path = original.REPORT / "source-lock.json"
    parent = read(
        checked(
            prior_path, read(original.REPORT / "qualification-lock.json")["files"][prior_path.name]
        )
    )
    earlier_path = exact.REPORT / "source-lock.json"
    earlier = read(
        checked(
            earlier_path, read(exact.REPORT / "qualification-lock.json")["files"][earlier_path.name]
        )
    )
    cases = {}
    for name, locked in parent["cases"].items():
        case = _load_case(name)
        path, digest = exact.lineage.locked_native(case, "capture")
        rows = read(checked(path, digest.removeprefix("sha256:")))["source"]["probes"]
        excluded = {row["visit"] for row in locked["rows"]}
        excluded.update(row["visit"] for row in earlier["cases"].get(name, {}).get("rows", []))
        fixtures = []
        for kind, (visit, probes) in choose(name, rows, excluded).items():
            segment, manifest, window = original.decode(case, visit)
            if any(p["valid_start_counter"] != window.acquisition["sample_start"] for p in probes):
                raise ValueError("selected archived factors have the wrong hardware counter")
            fixtures.append(
                dict(
                    kind=kind,
                    visit=visit,
                    segment=segment,
                    manifest=manifest,
                    iq_sha256=window.iq_sha256,
                    probes=probes,
                )
            )
        cases[name] = dict(
            {
                k: locked[k]
                for k in ("root", "cpu", "edge", "archive_sha256", "input_manifest", "sources")
            },
            rows=fixtures,
        )
        print(name, [(row["kind"], row["visit"]) for row in fixtures], flush=True)
    for name in ("batched32", "cfo", "fused"):
        if parent["libs"][name] != earlier["libraries"][name]:
            raise ValueError("original refiners differ from their independent qualification")
    source_paths = (
        Path(__file__),
        Path(prepared_hotpath.__file__),
        Path(anchor_grid.__file__),
        prior_path,
        earlier_path,
        REPORT / "PROTOCOL.md",
    )
    save_json(
        work / "input-lock.json",
        dict(
            cases=cases,
            libs=parent["libs"],
            python_sha256=parent["python_sha256"],
            sources={str(p): _sha(p) for p in source_paths},
            modes=MODES,
            repeats=RUNS,
        ),
    )


def sample(window, policy):
    wall, cpu = perf_counter_ns(), process_time_ns()
    result, probes = scan_capture_window(window, window.receiver_ids, policy)
    time = dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)
    if result.status != "processed" or len(probes) != 2:
        raise ValueError("complete dual-lane detector did not process the visit")
    return (result.model_dump(mode="json"), probes), time


def audit_grid(acquisition, window, policy, grid, fine):
    select = acquisition._retain_score_map_peaks
    gaps = []

    def audit(frequencies, scores, count, radius, separation, epochs):
        original_selected = select(frequencies, scores, count, radius, separation, epochs)
        alternate = anchor_grid.retained_peaks(
            frequencies, scores, count, radius, separation, epochs
        )
        if original_selected != alternate:
            raise ValueError("ordered selection changed on an identical prepared grid")
        gaps.extend(
            original.rank_gap(
                np.asarray(scores), np.asarray(frequencies), count, radius, separation
            )
        )
        return original_selected

    grid.calls.clear()
    with fine.route(), patch.object(acquisition, "_retain_score_map_peaks", audit):
        sample(window, policy)
    if not gaps or not all(c["applied"] for c in grid.calls):
        raise ValueError("genuine window lost its full coarse grid")
    return gaps


def worker(work, name):
    from leo.analysis.starlink import acquisition

    lock_path = work / "input-lock.json"
    lock = read(lock_path)
    cfg = lock["cases"][name]
    case = _load_case(name)
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("wrong replay CPU")
    checked(original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | cfg["sources"]).items():
        checked(Path(path), digest)
    _, policy, producer = exact.lineage.source_lineage(case)
    if (producer["capture"]["root"], producer["capture"]["input_manifest_sha256"]) != (
        cfg["root"],
        cfg["input_manifest"],
    ):
        raise ValueError("wrong installed capture release")
    libraries = {
        name: checked(Path(item["path"]), item["sha256"]) for name, item in lock["libs"].items()
    }
    grid = PersistentGrid(libraries["prepared"])
    fine = prepared_hotpath.FineWorkspace(acquisition)
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
            stock, installed_time = sample(window, policy)
            if stock[1] != fixture["probes"]:
                raise ValueError("installed producer disagrees with the frozen factor archive")
            clocks = defaultdict(list)
            with exact.refiners(libraries), grid.route(acquisition, exact.starts.screen_module()):
                for mode in MODES:
                    with arm(mode, fine):
                        observed, _ = sample(window, policy)
                    if observed != stock:
                        raise ValueError(
                            f"{name} visit {visit} warm {mode} changed complete detector output"
                        )
                for repetition in range(RUNS):
                    turn = (repetition + index) % len(MODES)
                    for order, mode in enumerate(MODES[turn:] + MODES[:turn]):
                        grid.calls.clear()
                        start = fine.applied, fine.fallbacks
                        with arm(mode, fine):
                            observed, timing = sample(window, policy)
                        if observed != stock:
                            raise ValueError(
                                f"{name} visit {visit} measured {mode} changed detector output"
                            )
                        clocks[mode].append(
                            dict(
                                **timing,
                                repetition=repetition,
                                order=order,
                                fine_calls=fine.applied - start[0],
                                fine_fallbacks=fine.fallbacks - start[1],
                                grid_calls=len(grid.calls),
                                inverse_ffts=sum(c["inverse_ffts"] for c in grid.calls),
                                full_grid=all(c["applied"] for c in grid.calls),
                            )
                        )
                gaps = audit_grid(acquisition, window, policy, grid, fine)
            records.append(
                dict(
                    visit=visit,
                    kind=fixture["kind"],
                    iq_sha256=window.iq_sha256,
                    installed=installed_time,
                    clocks=dict(clocks),
                    rank_gaps=gaps,
                    public=stock[0],
                    probes=stock[1],
                )
            )
            print(name, visit, fixture["kind"], flush=True)
    finally:
        grid.clear_cache()
    document = dict(
        case=name,
        cpu=cfg["cpu"],
        input_lock_sha256=_sha(lock_path),
        peak_rss_kib=exact.stages.resident()["hwm_kib"],
        workspace_bytes=fine.workspace_bytes,
        rows=records,
    )
    write(work / f"{name}.json.gz", gzip.compress(encoded(document), mtime=0))


def arm(mode, fine):
    if mode == "prepared":
        return nullcontext()
    if mode == "fine":
        return fine.route()
    return fine.route(selector=anchor_grid.retained_peaks)


def run(work, names):
    lock = read(work / "input-lock.json")
    for name in names:
        cfg = lock["cases"][name]
        env = os.environ | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        for prefix in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[prefix + "_NUM_THREADS"] = "1"
        subprocess.run(
            [
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
            ],
            cwd=ROOT,
            env=env,
            check=True,
            timeout=150,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "worker", "run"))
    parser.add_argument("work", type=Path)
    parser.add_argument("cases", nargs="*", choices=tuple(original.CASES))
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "worker":
        worker(args.work, args.cases[0])
    else:
        run(args.work, args.cases)
