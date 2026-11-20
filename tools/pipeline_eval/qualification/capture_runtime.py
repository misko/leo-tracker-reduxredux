"""Replay original installed acquisition and current wide GLRT on resident IQ."""

import argparse
import gzip
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants.selective_capture import visit_pairs
from ..variants.single_chain import analyze_native
from ..variants.staggered_native import RfStagger
from . import capture_detector_lineage as lineage
from . import capture_starts as previous
from .capture_detector_replay import scan_capture_window
from .full_v5_check import _from_native, _load_case, _probe, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/pilot-influence/capture-runtime"
WORK = Path("/srv/bulk/leo-dev/receiver-screening-20261119/capture-runtime-v2")
PRIOR_PIN = "af9794ca3b464184cf3f108230249ffcee7d129d5f10e62bce1a3e17e6720faa"
MODES = ("capture", "dual", "one")
CASES = ("DS26-0162", "DS26-0237", "DS29-0082", "DS29-0519")
EXPECTED = ((0, 1), (4, 64), (0, 2), (4, 155))
CURRENT = ROOT / "src/leo/analysis/starlink/native_short_window.py"


def checked(path, digest):
    if _sha(path) != digest:
        raise ValueError(f"installed or frozen input differs from its hash: {path}")
    return path


def read(path):
    return json.loads(path.read_bytes())


def choose(rows):
    return sorted(
        (
            min((r for r in rows if r["kind"] == tag), key=lambda x: x["visit"])
            for tag in ("matched", "miss")
        ),
        key=lambda x: x["visit"],
    )


def lanes(probes, last):
    switch = RfStagger()
    chosen = {}
    for visit, rows in visit_pairs(probes):
        if visit > last:
            break
        rf = rows[0]["actual_rf_hz"]
        if (
            [p["receiver_id"] for p in rows] != [0, 1]
            or not float(rf).is_integer()
            or rows[1]["actual_rf_hz"] != rf
        ):
            raise ValueError("source omitted a physical receiver or changed RF")
        chosen[visit] = switch.reserve(int(rf))
    return chosen


def decompress(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def freeze(work):
    from . import one_lane_arm as lane

    prior = read(checked(previous.REPORT / "result-lock.json", PRIOR_PIN))["files"]
    case_plan = read(checked(previous.REPORT / "input-lock.json", prior["input-lock.json"]))
    for name, digest in case_plan["sources"].items():
        lane.checked(Path(name), digest)
    oracle = lane.read(previous.ORACLE / "input-lock.json")["cases"]
    earlier = lane.read(
        lane.checked(lane.reuse.REPORT / "qualification-lock.json", lane.PREVIOUS_LOCK)
    )
    fixture_lock = lane.checked(
        lane.reuse.REPORT / "input-lock.json", earlier["files"]["input-lock.json"]
    )
    templates = {n: h for n, h in lane.read(fixture_lock)["files"].items() if n.endswith(".c16")}
    work.mkdir()
    roster = {}
    for ident, fixed in zip(CASES, EXPECTED, strict=True):
        case = _load_case(ident)
        chosen = choose(oracle[ident]["selected"])
        if tuple(r["visit"] for r in chosen) != fixed:
            raise ValueError("frozen positive and missed selections differ from the protocol")
        archive_path, native_hash = lineage.locked_native(case, "capture")
        archive = lane.read(lane.checked(archive_path, native_hash.removeprefix("sha256:")))
        schedule = lanes(archive["source"]["probes"], max(fixed))
        file = f"{ident}-capture.json.gz"
        previous_rows = decompress(lane.checked(previous.REPORT / file, prior[file]))
        prior_rows = {p["visit"]: p for p in previous_rows["capture"]}
        entries = []
        for item in chosen:
            v = item["visit"]
            old = prior_rows[v]
            if old["metadata"]["iq_sha256"] != item["iq_sha256"]:
                raise ValueError("prior IQ authority changed")
            entries.append(
                dict(
                    source=item,
                    selected_lane=schedule[v],
                    previous_capture=old["capture"]["probes"],
                )
            )
        runtime = Path(previous_rows["producer"]["python"])
        roster[ident] = dict(
            entries=entries,
            producer=case_plan["cases"][ident],
            python=str(runtime),
            python_sha256=_sha(runtime),
            native_capture_sha256=native_hash,
        )
    sources = (
        Path(__file__),
        CURRENT,
        Path(analyze_native.__code__.co_filename),
        REPORT / "PROTOCOL.md",
    )
    lane.checked(lane.WIDE_RUNTIME, lane.WIDE_PIN)
    save_json(
        work / "input-lock.json",
        dict(
            cases=roster,
            prior_lock_sha256=PRIOR_PIN,
            sources={str(p): _sha(p) for p in sources},
            current_wide_sha256=lane.WIDE_PIN,
            current_wide_path=str(lane.WIDE_RUNTIME),
            template_root=str(lane.reuse.WORK / "fixtures"),
            templates=templates,
            affinity=[7],
            repeats=2,
        ),
    )


def runtime_class():
    spec = importlib.util.spec_from_file_location("benchmark_current_native_short_window", CURRENT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.NativeShortWindow


def project_current(window, detector, mode, selected):
    response = (
        detector.analyze(window.samples)
        if mode == "dual"
        else analyze_native(detector, window.samples, selected)
    )
    by_lane = {r["receiver_id"]: r["candidates"] for r in response["rows"]}
    valid = [0, 1] if mode == "dual" else [selected]
    if list(by_lane) != valid:
        raise ValueError("current native analysis did not emit the scheduled physical receivers")
    return [
        _probe(window, i, (_from_native(rank, c) for rank, c in enumerate(by_lane.get(i, []))))
        for i in (0, 1)
    ]


def call(mode, window, policy, dual, single, selected):
    if mode == "capture":
        result, probes = scan_capture_window(window, window.receiver_ids, policy)
        if result.status != "processed":
            raise ValueError("original held visit became invalid")
        return probes
    return project_current(window, dual if mode == "dual" else single, mode, selected)


def worker(work, ident):
    lock = read(work / "input-lock.json")
    if os.sched_getaffinity(0) != set(lock["affinity"]):
        raise ValueError("worker affinity differs from the frozen paired benchmark")
    for name, digest in lock["sources"].items():
        checked(Path(name), digest)
    plan = lock["cases"][ident]
    case = _load_case(ident)
    capture, policy, producer = lineage.source_lineage(case)
    authority = plan["producer"]
    if (
        producer["capture"]["root"] != authority["producer"]
        or producer["capture"]["input_manifest_sha256"] != authority["input_manifest_sha256"]
    ):
        raise ValueError("worker is not using the sealed capture installation")
    for name, digest in authority["sources"].items():
        checked(Path(name), digest)
    library = checked(Path(lock["current_wide_path"]), lock["current_wide_sha256"])
    windows = [previous.hinted_glrt_trial.load_selected(case, p["source"]) for p in plan["entries"]]
    capsule = Path(lock["template_root"]) / capture["edge"]
    filenames = [f"{capture['edge']}-{k}.c16" for k in ("exact", "control")]
    templates = [
        np.fromfile(checked(capsule / k, lock["templates"][f"{capture['edge']}/{k}"]), dtype="<c16")
        for k in filenames
    ]
    opts = dict(sample_rate_hz=10_000_000, fractional_epoch=True)
    installed = runtime_class()
    measured, warmed = [], {}
    with (
        installed(str(library), *templates, receiver_count=2, **opts) as dual,
        installed(str(library), *templates, receiver_count=1, **opts) as single,
    ):
        for mode in MODES:
            wall, cpu = perf_counter_ns(), process_time_ns()
            output = call(
                mode, windows[0], policy, dual, single, plan["entries"][0]["selected_lane"]
            )
            warmed[mode] = dict(
                wall_ns=perf_counter_ns() - wall, cpu_ns=process_time_ns() - cpu, probes=output
            )
        for repeat in range(lock["repeats"]):
            for index, (window, row) in enumerate(zip(windows, plan["entries"], strict=True)):
                offset = (CASES.index(ident) + index + repeat) % len(MODES)
                for mode in MODES[offset:] + MODES[:offset]:
                    wall, cpu = perf_counter_ns(), process_time_ns()
                    probes = call(mode, window, policy, dual, single, row["selected_lane"])
                    measured.append(
                        dict(
                            visit=row["source"]["visit"],
                            repeat=repeat,
                            mode=mode,
                            wall_ns=perf_counter_ns() - wall,
                            cpu_ns=process_time_ns() - cpu,
                            probes=probes,
                        )
                    )
                print(ident, row["source"]["visit"], repeat, flush=True)
    write(
        work / f"{ident}.json.gz",
        gzip.compress(
            encoded(
                dict(
                    producer=producer,
                    templates={str(p): _sha(p) for p in capsule.glob("*.c16")},
                    input_lock_sha256=_sha(work / "input-lock.json"),
                    measurements=measured,
                    warmup=warmed,
                )
            ),
            mtime=0,
        ),
    )


def run(work):
    inputs = read(work / "input-lock.json")
    for ident in CASES:
        entry = inputs["cases"][ident]
        executable = checked(Path(entry["python"]), entry["python_sha256"])
        env = os.environ | {"PYTHONPATH": entry["producer"]["producer"] + ":" + str(ROOT)}
        for name in ("OMP", "OPENBLAS", "MKL", "VECLIB_MAXIMUM", "NUMEXPR", "BLIS"):
            env[name + "_NUM_THREADS"] = "1"
        command = [str(executable), "-u", "-m", __spec__.name, "worker", str(work), "--case", ident]
        outcome = subprocess.run(command, cwd=ROOT, env=env, check=False, timeout=65)
        if outcome.returncode:
            raise SystemExit(f"{ident} installed worker exited {outcome.returncode}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("freeze", "run", "worker"))
    p.add_argument("work", type=local_output, default=WORK, nargs="?")
    p.add_argument("--case", choices=CASES)
    a = p.parse_args()
    if a.action == "worker":
        worker(a.work, a.case)
    elif a.action == "freeze":
        freeze(a.work)
    else:
        run(a.work)
