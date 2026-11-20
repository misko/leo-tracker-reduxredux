"""Time the full original dual detector with an eight-anchor peer retry."""

import argparse
import csv
import gzip
import os
import subprocess
from collections import defaultdict
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import peer_retry, prepared_hotpath_peaks
from ..variants.fine_search import FineSearch
from ..variants.original_kernel import PersistentGrid
from ..variants.selective_capture import visit_pairs
from . import capture_starts
from . import single_pass_trial as previous
from .capture_runtime import checked, read
from .field_exact_waveform import PANEL as FINE_PANEL
from .full_v5_check import BULK, _load_case, _sha
from .peer_retry_support import PRIMARY, REPORT, verified

BLIND = "outcome-blind"
RESCUE = "known-rescue"
REPEATS = 3
CPUS = (4, 5)
MEMORY = 512 * 1024 * 1024


def chosen(values, count, ident, cohort):
    def key(visit):
        return sha256(encoded(["peer-retry-v1", cohort, ident, visit])).digest()

    return sorted(values, key=key)[:count]


def freeze(work):
    historical = verified(previous.REPORT, "qualification-lock.json", "input-lock.json")
    fine = verified(FINE_PANEL, "qualification-lock.json", "input-lock.json")
    changed = verified(PRIMARY, "prediction-lock.json", "changed-visits.csv")
    assay = read(historical)
    panel = read(fine)
    if any(panel["libs"][key] != value for key, value in assay["libs"].items()):
        raise ValueError("the prepared paths do not share compatible refiners")
    support = REPORT / "primary-support.json"
    if read(support)["probes"] != 448:
        raise ValueError("complete proposal support must precede the waveform experiment")
    with changed.open(newline="") as stream:
        rescued = defaultdict(list)
        for row in csv.DictReader(stream):
            if row["conditional_positive"] == "True" and row["primary_positive"] == "False":
                rescued[int(row["receiver"])].append(int(row["visit"]))
    cases, sources = {}, {}
    for ident, binding in assay["cases"].items():
        case = _load_case(ident)
        archive = checked(BULK / case["native"]["path"], case["native"]["sha256"])
        pairs = dict(visit_pairs(read(archive)["source"]["probes"]))
        known = verified(previous.REPORT, "qualification-lock.json", f"{ident}.json.gz")
        roster = previous.read_gzip(known)
        if roster["input_lock_sha256"] != _sha(historical):
            raise ValueError("prior retry outcomes lack the original source binding")
        blind = chosen(pairs.keys() - {r["visit"] for r in roster["rows"]}, 10, ident, BLIND)
        if ident == "DS26-0237":
            rescue = [
                v
                for lane in rescued.values()
                for v in chosen(set(lane) - set(blind), 6, ident, RESCUE)
            ]
        else:
            rescue = [
                row["visit"]
                for row in roster["rows"]
                if any(
                    attempt[1] == 22 and attempt[2]
                    for attempt in row["evidence"]["conditional"]["attempts"]
                )
            ]
        rows = []
        for visit in sorted(blind + rescue):
            segment, sequence, manifest, digest = previous.original.locate(case, visit)
            rows.append(
                dict(
                    visit=visit,
                    segment=segment,
                    sequence=sequence,
                    manifest=str(manifest),
                    manifest_sha256=digest,
                    probes=pairs[visit],
                    cohort=RESCUE if visit in rescue else BLIND,
                )
            )
        cases[ident] = dict(producer=binding["producer"], rows=rows)
        sources[str(known)] = _sha(known)
        print(ident, "blind", blind, "rescue", rescue, flush=True)
    for path in (
        historical,
        fine,
        changed,
        support,
        Path(peer_retry.__file__),
        Path(__file__),
        REPORT / "PROTOCOL.md",
        Path(previous.__file__),
    ):
        sources[str(path)] = _sha(path)
    sources.update(panel["sources"])
    lock = dict(
        cases=cases,
        sources=sources,
        libs=panel["libs"],
        python_sha256=panel["python_sha256"],
        repeats=REPEATS,
        modes=peer_retry.MODES,
    )
    work.mkdir(exist_ok=False)
    for path in (work / "input-lock.json", REPORT / "input-lock.json"):
        save_json(path, lock)


def observations(attempts):
    return [
        dict(row, public=[asdict(candidate) for candidate in row["public"]]) for row in attempts
    ]


def call(window, mode, policy, analysis, detector, acquisition, grid, *, trace=False):
    grid.calls.clear()
    with peer_retry.route(analysis, detector, acquisition, mode, trace=trace) as attempts:
        result, clock = previous.prepared_hotpath_trial.sample(window, policy)
    main = attempts[:2]
    retry = attempts[2:]
    expected = (
        []
        if mode == "primary12" or sum(r["gate"] for r in main) != 1
        else [next(r["receiver"] for r in main if not r["gate"])]
    )
    if (
        [(r["receiver"], len(r["anchors"])) for r in main] != [(0, 12), (1, 12)]
        or [r["receiver"] for r in retry] != expected
        or any(len(r["anchors"]) != (8 if mode == "complement8" else 22) for r in retry)
        or not all(r["applied"] for r in grid.calls)
        or not len(attempts) <= len(grid.calls) <= 2 * len(attempts)
    ):
        raise ValueError("live detector did not run its exact planned physical attempt sequence")
    final = {r["receiver"]: r["gate"] for r in attempts}
    if [final[rx] for rx in (0, 1)] != list(map(previous.positive, result[1])):
        raise ValueError("projected factors changed the live retry gate")
    return (
        dict(public=result[0], probes=result[1], attempts=observations(attempts)),
        dict(
            **clock,
            grids=len(grid.calls),
            retry_grids=sum(r["anchors"] != 12 for r in grid.calls),
            coarse_cpu_ns=sum(r["config_cpu_ns"] + r["native_cpu_ns"] for r in grid.calls),
        ),
    )


def bind(work, ident, cpu):
    lock = read(work / "input-lock.json")
    case = lock["cases"][ident]
    producer = case["producer"]
    if os.sched_getaffinity(0) != {cpu}:
        raise ValueError("peer retry is running off its assigned CPU")
    checked(previous.original.PYTHON, lock["python_sha256"])
    for path, digest in (lock["sources"] | producer["sources"]).items():
        checked(Path(path), digest)
    capture, policy, observed = previous.exact.lineage.source_lineage(_load_case(ident))
    if (
        observed["capture"]["root"],
        capture["edge"],
        observed["capture"]["input_manifest_sha256"],
    ) != (producer["producer"], producer["edge"], producer["input_manifest_sha256"]):
        raise ValueError("wrong original measurement producer")
    libs = {k: checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    return case, policy, libs


def worker(work, ident, cpu):
    from leo.analysis.starlink import acquisition
    from leo.scanner import fast_scan_analysis, fast_scan_detector

    case, policy, libs = bind(work, ident, cpu)
    grid = PersistentGrid(libs["prepared"])
    fine = FineSearch(libs["fine"], acquisition)
    if not fine.compatible:
        raise ValueError("original fine search ABI did not pass the binary64 sentinel")
    rows = []
    try:
        with (
            previous.exact.refiners(libs),
            grid.route(acquisition, capture_starts.screen_module()),
            patch.object(
                acquisition,
                "_retain_score_map_peaks",
                prepared_hotpath_peaks.retained_peaks,
            ),
            fine.route(),
        ):
            for index, (fixture, window) in enumerate(previous.load_windows(case["rows"])):

                def run(mode, trace=False, window=window):
                    return call(
                        window,
                        mode,
                        policy,
                        fast_scan_analysis,
                        fast_scan_detector,
                        acquisition,
                        grid,
                        trace=trace,
                    )

                baseline, _ = run("conditional", trace=True)
                traces = baseline["attempts"]
                for row in traces:
                    row["proposals"] = {key: row.pop(key) for key in ("coarse", "acquired")}
                traces = [r.pop("proposals") for r in traces]
                evidence = {"conditional": baseline}
                evidence.update({m: run(m)[0] for m in peer_retry.MODES if m != "conditional"})
                if encoded(baseline["probes"]) != encoded(fixture["probes"]):
                    raise ValueError("timed reference differs from the signed original archive")
                for alt in ("primary12", "complement8"):
                    if evidence[alt]["attempts"][:2] != baseline["attempts"][:2]:
                        raise ValueError(
                            "the intervention changed one of the two original primaries"
                        )
                    if len(baseline["attempts"]) == 2 and evidence[alt] != baseline:
                        raise ValueError("a visit without an original retry changed")
                timings = []
                for repeat in range(REPEATS):
                    order = (index + repeat) % len(peer_retry.MODES)
                    mixed = peer_retry.MODES[order:] + peer_retry.MODES[:order]
                    for slot, mode in enumerate(mixed):
                        result, clock = run(mode)
                        if encoded(result) != encoded(evidence[mode]):
                            raise ValueError("repeated full detector call changed public evidence")
                        timings.append(dict(mode=mode, repeat=repeat, slot=slot, **clock))
                rows.append(
                    dict(
                        visit=fixture["visit"],
                        cohort=fixture["cohort"],
                        iq_sha256=window.iq_sha256,
                        traces=traces,
                        methods=evidence,
                        timings=timings,
                    )
                )
                print(ident, fixture["visit"], fixture["cohort"], flush=True)
    finally:
        grid.clear_cache()
    if fine.fallbacks:
        raise ValueError("the tested original fine-search runtime left its qualified path")
    write(
        work / f"{ident}.json.gz",
        gzip.compress(
            encoded(
                dict(
                    case=ident,
                    cpu=cpu,
                    rows=rows,
                    fine_calls=fine.calls,
                    peak_rss_kib=previous.exact.stages.resident()["hwm_kib"],
                    input_lock_sha256=_sha(work / "input-lock.json"),
                )
            ),
            mtime=0,
        ),
    )


def run(work, ident, cpu):
    if cpu not in CPUS:
        raise ValueError("stay on the two released host CPU cores")
    producer = read(work / "input-lock.json")["cases"][ident]["producer"]["producer"]
    env = [f"PYTHONPATH={producer}:{ROOT}"]
    env.extend(
        f"{prefix}_NUM_THREADS=1"
        for prefix in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS")
    )
    unit = f"leo-peer-retry-{cpu}-{uuid4().hex[:8]}"
    args = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        "--unit=" + unit,
        "--working-directory=" + str(ROOT),
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        "--property=RuntimeMaxSec=300s",
        "taskset",
        "-c",
        str(cpu),
        "env",
        *env,
        str(previous.original.PYTHON),
        "-Bu",
        "-m",
        __spec__.name,
        "worker",
        str(work),
        ident,
        str(cpu),
    ]
    with (work / f"{ident}.log").open("xb") as log:
        subprocess.run(args, check=True, timeout=320, stdout=log, stderr=subprocess.STDOUT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "run", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("case", choices=previous.CASE_IDS, nargs="?")
    parser.add_argument("cpu", type=int, choices=CPUS, nargs="?")
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.case is None or args.cpu is None:
        parser.error("a case and CPU are required")
    else:
        (worker if args.action == "worker" else run)(args.work, args.case, args.cpu)
