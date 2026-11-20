"""Measure unpruned exact/control FFT changes in the complete original detector."""

import argparse
import gzip
import os
import subprocess
from contextlib import nullcontext
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import process_time_ns
from unittest.mock import patch

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import fine_search, first_gate, prepared_hotpath_peaks, spectral_rewrite
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import first_gate_trial as prior
from .full_v5_check import BULK, _load_case, _sha
from .winner_bound_spectrum import component

REPORT = prior.REPORT.parents[1] / "original-schedule/spectral-rewrite"
RAW_PIN = "235eee88a9cb7e803e3b02b517c1210bda594cfd86acec1e98f1c4b964898651"
MODES = ("stock", "split", "batched")
REPEATS = 5
CPU = 13
original = prior.prior.original
baseline = prior.prior.previous
read, checked = whole_iq.read, whole_iq.checked


def tie(probe):
    passing = sorted(
        (c["fractional_margin"] for c in probe["candidates"] if c["passed_fractional_margin_gate"]),
        reverse=True,
    )
    return len(passing) >= 2 and passing[0] == passing[1]


def make_tie(case, existing):
    document = read(checked(BULK / case["native"]["path"], case["native"]["sha256"]))
    key = document["source"]["input_manifest_sha256"]
    pool = (
        (v, p)
        for v, p in visit_pairs(document["source"]["probes"])
        if v < 256 and v not in existing and any(map(tie, p))
    )
    visit, probes = min(
        pool,
        key=lambda item: (
            sha256(f"spectral-rewrite-v1|{key}|{item[0]}".encode()).digest(),
            item[0],
        ),
    )
    segment, manifest, raw = original.decode(case, visit)
    if any(r["valid_start_counter"] != raw.acquisition["sample_start"] for r in probes):
        raise ValueError("archived tie should refer to this exact physical stereo visit")
    return dict(
        kind="passing-tie",
        visit=visit,
        segment=segment,
        manifest=manifest,
        iq_sha256=raw.iq_sha256,
        probes=probes,
    )


def freeze(work, cpu):
    if (REPORT / "input-lock.json").exists():
        raise FileExistsError("choose a separate report for another frozen replay")
    seal = read(checked(prior.REPORT / "qualification-lock.json", RAW_PIN))
    path = checked(prior.REPORT / "input-lock.json", seal["files"]["input-lock.json"])
    plan = read(path)
    cases = {}
    for name, cfg in plan["cases"].items():
        case = _load_case(name)
        earlier = cfg["rows"]
        selected = make_tie(case, {v["visit"] for v in earlier})
        cases[name] = dict(cfg, cpu=cpu, rows=[*earlier, selected])
    exact_sources = (
        Path(__file__),
        Path(spectral_rewrite.__file__),
        Path(component.__code__.co_filename),
    )
    sources = plan["sources"] | {str(p): _sha(p) for p in (*exact_sources, REPORT / "PROTOCOL.md")}
    lock = dict(
        cases=cases,
        libs=plan["libs"],
        sources=sources,
        python_sha256=plan["python_sha256"],
        modes=MODES,
        repeats=REPEATS,
        parent_qualification_sha256=RAW_PIN,
    )
    work.mkdir()
    save_json(work / "input-lock.json", lock)
    save_json(REPORT / "input-lock.json", lock)


def variant(producer, method):
    if method == "stock":
        return producer._glrt_pair, 0
    implementation = spectral_rewrite.PairSpectrum(producer, component, batched=method == "batched")
    return implementation.scores, implementation.workspace.nbytes if method == "batched" else 0


def worker(work, name, memory):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.scanner import fast_scan_detector

    path = checked(work / "input-lock.json", _sha(REPORT / "input-lock.json"))
    lock = read(path)
    cfg = lock["cases"][name]
    if os.sched_getaffinity(0) != {cfg["cpu"]}:
        raise ValueError("the matched full-detector A/B requires its assigned CPU")
    checked(original.PYTHON, lock["python_sha256"])
    for item, sha in (lock["sources"] | cfg["sources"]).items():
        checked(Path(item), sha)
    if Path(fast_scan_detector.__file__) != Path(cfg["root"]) / "leo/scanner/fast_scan_detector.py":
        raise ValueError("detector resolves in a different installed producer")
    case = _load_case(name)
    _, policy, lineage = baseline.exact.lineage.source_lineage(case)
    if (lineage["capture"]["root"], lineage["capture"]["input_manifest_sha256"]) != (
        cfg["root"],
        cfg["input_manifest"],
    ):
        raise ValueError("different producer or capture authorization")
    libs = {n: checked(Path(v["path"]), v["sha256"]) for n, v in lock["libs"].items()}
    grid = PersistentGrid(libs["prepared"])
    fine = fine_search.FineSearch(libs["fine"], acquisition)
    if not fine.compatible:
        raise ValueError("fine arithmetic sentinel failed")
    methods = (memory,) if memory else MODES
    replacements = {mode: variant(fast_scan_scores, mode) for mode in methods}
    manifests = []
    try:
        for index, fixture in enumerate(cfg["rows"]):
            if memory and fixture["kind"] != "passing-tie":
                continue
            segment, digest, window = original.decode(case, fixture["visit"])
            if (segment, digest, window.iq_sha256) != (
                fixture["segment"],
                fixture["manifest"],
                fixture["iq_sha256"],
            ):
                raise ValueError("frozen resident IQ differs from the planned recording")
            peak_before_kib = getrusage(RUSAGE_SELF).ru_maxrss
            with (
                baseline.exact.refiners(libs),
                grid.route(acquisition, baseline.exact.starts.screen_module()),
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                ),
                fine.route(),
            ):

                def measure(mode, *, profile=False, resident=window):
                    scorer, workspace = replacements[mode]
                    grid.calls.clear()
                    attempts = first_gate.GateStop(fast_scan_detector, None)
                    scope = []

                    def measured(exact, noise, *, size=512):
                        start = process_time_ns()
                        result = scorer(exact, noise, size=size)
                        scope.append(process_time_ns() - start)
                        return result

                    lane = attempts.route() if profile else nullcontext()
                    with (
                        lane,
                        patch.object(
                            fast_scan_scores, "_glrt_pair", measured if profile else scorer
                        ),
                    ):
                        output, clock = baseline.sample(resident, policy)
                    if not grid.calls or not all(item["applied"] for item in grid.calls):
                        raise ValueError("original prepared folded search was not fully applied")
                    candidate = dict(
                        clock,
                        mode=mode,
                        coarse_grids=len(grid.calls),
                        workspace_bytes=workspace,
                        spectrum_calls=len(scope) if profile else None,
                        spectrum_cpu_ns=sum(scope) if profile else None,
                        peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
                    )
                    return encoded(output), output, candidate, attempts.attempts

                checks, profiles, samples = [], [], []
                control = None
                for mode in methods:
                    payload, output, clocks, attempts = measure(mode, profile=not memory)
                    if control is None:
                        control = payload
                        control_attempts = attempts
                    if payload != control or output[1] != fixture["probes"]:
                        raise ValueError("public output or archived projection changed")
                    if not memory:
                        receipt = prior.compare_attempts(control_attempts, attempts, None)
                        checks.append(dict(mode=mode, receiver_attempts=receipt))
                        profiles.append(clocks)
                if not memory:
                    for rep in range(REPEATS):
                        shift = (index + rep) % len(methods)
                        order = methods[shift:] + methods[:shift]
                        if rep % 2:
                            order = order[::-1]
                        for place, mode in enumerate(order):
                            payload, _, clocks, _ = measure(mode)
                            if (
                                payload != control
                                or clocks["coarse_grids"] != profiles[0]["coarse_grids"]
                            ):
                                raise ValueError("timed detector changed an original public field")
                            samples.append(dict(clocks, repetition=rep, ordinal=place))
            manifests.append(
                dict(
                    visit=fixture["visit"],
                    kind=fixture["kind"],
                    iq_sha256=fixture["iq_sha256"],
                    output_sha256=sha256(control).hexdigest(),
                    attempts=checks,
                    samples=samples,
                    profiles=profiles,
                    before_memory_kib=peak_before_kib,
                    detector_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
                    workspace_bytes=replacements[methods[0]][1],
                )
            )
            print(name, fixture["visit"], fixture["kind"], memory or "timed", flush=True)
    finally:
        grid.clear_cache()
    suffix = f"-memory-{memory}" if memory else ""
    write(work / f"{name}{suffix}.json.gz", gzip.compress(encoded(manifests), mtime=0))


def run(work, *, memory=False):
    path = checked(work / "input-lock.json", _sha(REPORT / "input-lock.json"))
    lock = read(path)
    for name, cfg in lock["cases"].items():
        env = os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"}
        for method in MODES if memory else (None,):
            cmd = [
                "taskset",
                "-c",
                str(cfg["cpu"]),
                str(original.PYTHON),
                "-Bu",
                "-m",
                __spec__.name,
                "worker",
                str(work),
                "--id",
                name,
            ]
            if method is not None:
                cmd.extend(("--measure-memory", method))
            subprocess.run(cmd, cwd=ROOT, env=env, check=True, timeout=150)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "memory", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--cpu", type=int, default=CPU)
    parser.add_argument("--id")
    parser.add_argument("--measure-memory", choices=MODES)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work, args.cpu)
    elif args.action == "worker":
        worker(args.work, args.id, args.measure_memory)
    else:
        run(args.work, memory=args.action == "memory")


if __name__ == "__main__":
    main()
