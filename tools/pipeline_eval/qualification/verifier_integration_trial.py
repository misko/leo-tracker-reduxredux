"""Benchmark the original scanner with a persistent in-process portable verifier."""

import argparse
import gzip
import os
import subprocess
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, nullcontext
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np

from .. import whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from ..variants import fine_search, prepared_hotpath_peaks, verifier_integration
from ..variants.original_kernel import PersistentGrid
from . import capture_exact_trial as exact
from . import original_kernel_trial as original
from .capture_detector_replay import scan_capture_window
from .full_v5_check import _load_case, _sha
from .portable_fine_fixture import parent_lock

REPORT = ROOT / "reports/2026_11_19_receiver_screening/original-schedule/verifier-integration"
CASES = {"DS26-0237": 16, "DS29-0082": 17, "DS29-0519": 16}
MODES = ("installed", "prepared", "portable_installed", "portable_prepared")
REPEATS = 3
GATE = 0.025
EXCLUDED = {1561, 3235, 5855}
BRIDGE = Path(verifier_integration.__file__).with_suffix(".c")
PORTABLE_MANIFEST = REPORT.parent.parent / "coarse-and-navigation/portable-verifier/manifest.json"
PORTABLE_PIN = "481a79c7581330d68dfd1ed5dd35e4fe27bac4bc77c1a3996d4907e782a6b9ec"


def archive(case):
    path, digest = exact.lineage.locked_native(case, "capture")
    native = whole_iq.read(whole_iq.checked(path, digest))
    if native["source"]["session_id"] != case["session_id"]:
        raise ValueError("the archived factors identify a different recording")
    return path, digest, native


def select(ident, native):
    groups = defaultdict(list)
    for probe in native["source"]["probes"]:
        visit = probe["visit_index"]
        if visit >= 512 and visit not in EXCLUDED:
            groups[visit].append(probe)
    possible = {
        visit: probes
        for visit, probes in groups.items()
        if [p["receiver_id"] for p in probes] == [0, 1]
    }

    def values(probes):
        return [[c["fractional_margin"] for c in p["candidates"]] for p in probes]

    def equivalent(probes):
        for probe in probes:
            seen = {}
            for candidate in probe["candidates"]:
                key = candidate["integer_epoch_sample"]
                previous = seen.setdefault(key, candidate)
                if (
                    previous is not candidate
                    and abs(
                        previous["fractional_tracking_cfo_hz"]
                        - candidate["fractional_tracking_cfo_hz"]
                    )
                    < 1e-9
                    and abs(previous["fractional_margin"] - candidate["fractional_margin"]) < 2e-12
                ):
                    return True
        return False

    selected = []
    for kind in ("rejected", "dilute", "equivalent", "stereo"):
        options = []
        for visit, probes in possible.items():
            margins = values(probes)
            positives = [sum(m >= GATE for m in lane) for lane in margins]
            highest = max((m for lane in margins for m in lane), default=-1)
            qualifies = {
                "rejected": sum(positives) == 0 and 0.01 <= highest < GATE,
                "dilute": sum(positives) == 1 and highest < 0.06,
                "equivalent": equivalent(probes),
                "stereo": all(n >= 2 for n in positives),
            }[kind]
            if qualifies:
                options.append(visit)
        if not options:
            raise ValueError(f"no eligible {kind} visit for {ident}")
        visit = min(
            options,
            key=lambda i: sha256(encoded(["verifier-integration-v1", ident, kind, i])).hexdigest(),
        )
        selected.append(dict(visit=visit, kind=kind, archived=possible.pop(visit)))
    return selected


def build(work):
    from . import portable_verifier_run as build_portable

    portable = whole_iq.read(whole_iq.checked(PORTABLE_MANIFEST, PORTABLE_PIN))
    for source in build_portable.SOURCES[1:]:
        expected = portable["sources"][f"source/{source.name}.gz"]
        whole_iq.checked(source, expected)
    binary = work / "verifier-integration.so"
    command = [
        "cc",
        *(f for f in build_portable.BUILD_FLAGS if f != "-static"),
        "-march=x86-64-v3",
        "-fPIC",
        "-shared",
        "-I",
        build_portable.KERNEL / "native_presence",
        BRIDGE,
        *build_portable.SOURCES[1:],
        "-lm",
        "-o",
        binary,
    ]
    subprocess.run(
        command, cwd=work, env=os.environ | {"TMPDIR": str(work)}, check=True, timeout=30
    )
    return dict(
        path=str(binary),
        sha256=_sha(binary),
        command=list(map(str, command)),
        sources={str(p): _sha(p) for p in (BRIDGE, *build_portable.SOURCES[1:])},
    )


def freeze(work):
    prior = parent_lock()
    plans = {}
    for ident, cpu in CASES.items():
        case = _load_case(ident)
        path, digest, reference = archive(case)
        planned = select(ident, reference)
        selected = {r["visit"] for r in prior["cases"][ident]["rows"]}
        if selected & {r["visit"] for r in planned}:
            raise ValueError("held relay roster overlaps the earlier verifier tuning sample")
        plans[ident] = dict(
            prior["cases"][ident], rows=planned, cpu=cpu, archive=str(path), archive_sha256=digest
        )
    work.mkdir(mode=0o755)
    built = build(work)
    lock = dict(
        cases=plans,
        libs=prior["libs"],
        reference_sources=prior["sources"],
        bridge=built,
        portable_parent=PORTABLE_PIN,
        modes=MODES,
        repeats=REPEATS,
        python_sha256=prior["python_sha256"],
    )
    save_json(work / "input-lock.json", lock)


def validate(work, ident):
    from leo.analysis.starlink import acquisition

    lock = whole_iq.read(work / "input-lock.json")
    cfg = lock["cases"][ident]
    if os.sched_getaffinity(0) != {cfg["cpu"]} or not Path(acquisition.__file__).is_relative_to(
        cfg["root"]
    ):
        raise ValueError("sandbox worker lost its authentic producer or pinned CPU")
    whole_iq.checked(original.PYTHON, lock["python_sha256"])
    for filename, digest in (lock["reference_sources"] | cfg["sources"]).items():
        whole_iq.checked(Path(filename), digest)
    return lock, cfg


def stage(work, ident):
    _, cfg = validate(work, ident)
    case = _load_case(ident)
    _, _, lineage = exact.lineage.source_lineage(case)
    if lineage["capture"]["input_manifest_sha256"] != cfg["input_manifest"]:
        raise ValueError("saved capture manifest changed")
    folder = work / ident
    folder.mkdir()
    staged = []
    for entry in cfg["rows"]:
        visit = entry["visit"]
        segment, manifest, window = original.decode(case, visit)
        if any(
            p["valid_start_counter"] != window.acquisition["sample_start"]
            for p in entry["archived"]
        ):
            raise ValueError("archive factor and decoded capture do not share a physical counter")
        sample = memoryview(window.samples).cast("B")
        if sha256(sample).hexdigest() != window.iq_sha256.removeprefix("sha256:"):
            raise ValueError("staged samples differ from their authenticated CI16")
        name = f"{visit}.ci16"
        write(folder / name, sample)
        staged.append(
            dict(
                visit=visit,
                segment=segment,
                manifest_sha256=manifest,
                filename=name,
                sequence=window.sequence,
                iq_sha256=window.iq_sha256,
                acquisition=window.acquisition,
                target=window.target,
                sample_rate_hz=window.sample_rate_hz,
            )
        )
    save_json(
        folder / "resident-lock.json",
        dict(staged=staged, lineage=lineage, input_lock_sha256=_sha(work / "input-lock.json")),
    )


def resident(work, ident):
    from leo.scanner.fast_scan_analysis import VerifiedFastWindow

    folder = work / ident
    source = whole_iq.read(folder / "resident-lock.json")
    if source["input_lock_sha256"] != _sha(work / "input-lock.json"):
        raise ValueError("resident waveform belongs to a different frozen roster")
    result = {}
    for item in source["staged"]:
        path = whole_iq.checked(folder / item["filename"], item["iq_sha256"])
        samples = np.frombuffer(path.read_bytes(), dtype="<i2").reshape(200_000, 2, 2)
        result[item["visit"]] = VerifiedFastWindow(
            item["sequence"],
            item["iq_sha256"],
            item["acquisition"],
            item["target"],
            samples,
            sample_rate_hz=item["sample_rate_hz"],
        )
    return result


def resources():
    fields = {"VmRSS", "VmHWM", "VmSize"}
    return {
        key: int(value.split()[0])
        for line in Path("/proc/self/status").read_text().splitlines()
        if (pair := line.split(":", 1)) and len(pair) == 2
        for key, value in (pair,)
        if key in fields
    }


def detector_packet(window, policy, port):
    with port.bind(window) if port else nullcontext():
        result, factors = scan_capture_window(window, (0, 1), policy)
        return dict(public=result.model_dump(mode="json"), native=factors)


def audit_call(window, policy, port, acquisition, detector):
    original_probe = detector._evaluate_probe
    original_fine = acquisition._normalized_frame_scores
    calls = []

    def trace_fine(values, template, rate, epoch, frequencies, symbols):
        calls[-1]["original_grids"].append((int(epoch), len(frequencies), frequencies[0]))
        return original_fine(values, template, rate, epoch, frequencies, symbols)

    def trace_probe(*args, **settings):
        info = dict(
            receiver=settings["receiver_id"],
            anchors=settings["acquisition_config"].anchor_symbols,
            original_grids=[],
        )
        calls.append(info)
        result = original_probe(*args, **settings)
        info["packet"] = dict(
            candidates=[asdict(c) for c in result.candidates],
            hits=[hit.model_dump(mode="json") for hit in result.hits],
        )
        return result

    with (
        patch.object(detector, "_evaluate_probe", trace_probe),
        patch.object(acquisition, "_normalized_frame_scores", trace_fine),
    ):
        result = detector_packet(window, policy, port)
    native = list(port.calls) if port else []
    return result, dict(scheduler=calls, native=native)


def worker(work, ident, mode):
    from leo.analysis.starlink import acquisition, fast_scan_scores
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner import fast_scan_detector

    lock, cfg = validate(work, ident)
    windows = resident(work, ident)
    libraries = {k: whole_iq.checked(Path(v["path"]), v["sha256"]) for k, v in lock["libs"].items()}
    portable = mode.startswith("portable_")
    prepared = mode.endswith("prepared")
    policy = FastScanPolicyV2()
    initial_memory = resources()
    start, cpu = perf_counter_ns(), process_time_ns()
    with ExitStack() as stack:
        if prepared:
            grid = PersistentGrid(libraries["prepared"])
            stack.callback(grid.clear_cache)
            stack.enter_context(grid.route(acquisition, exact.starts.screen_module()))
            stack.enter_context(
                patch.object(
                    acquisition, "_retain_score_map_peaks", prepared_hotpath_peaks.retained_peaks
                )
            )
        if mode == "prepared":
            stack.enter_context(exact.refiners(libraries))
            pruned = fine_search.FineSearch(libraries["fine"], acquisition)
            if not pruned.compatible:
                raise ValueError("exact prepared scorer sentinel failed")
            stack.enter_context(pruned.route())
        port = None
        if portable:
            bridge = lock["bridge"]
            library = whole_iq.checked(Path(bridge["path"]), bridge["sha256"])
            port = verifier_integration.Port(
                library, acquisition, fast_scan_detector, fast_scan_scores, cfg["edge"]
            )
            stack.callback(port.close)
            stack.enter_context(port.route())
        setup = dict(
            cpu_ns=process_time_ns() - cpu,
            wall_ns=perf_counter_ns() - start,
            memory=resources(),
            context_bytes=port.workspace_bytes if port else 0,
        )
        rows = []
        for entry in cfg["rows"]:
            visit = entry["visit"]
            window = windows[visit]
            cold_wall, cold_cpu = perf_counter_ns(), process_time_ns()
            cold = detector_packet(window, policy, port)
            ready = dict(cpu_ns=process_time_ns() - cold_cpu, wall_ns=perf_counter_ns() - cold_wall)
            observed, trace = audit_call(window, policy, port, acquisition, fast_scan_detector)
            if observed != cold or observed["public"]["status"] != "processed":
                raise ValueError("instrumentation changed the native detector output or validity")
            timings = []
            for repeat in range(REPEATS):
                wall, cpu = perf_counter_ns(), process_time_ns()
                packet = detector_packet(window, policy, port)
                timing = dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)
                if packet != observed:
                    raise ValueError("repeated detector output changed within its own arm")
                timings.append(dict(timing, repeat=repeat, memory=resources()))
            rows.append(
                dict(
                    visit=visit,
                    kind=entry["kind"],
                    output=observed,
                    trace=trace,
                    first_call=ready,
                    repeats=timings,
                )
            )
            print(ident, mode, visit, tuple(r["route"] for r in trace["native"]), flush=True)
        payload = dict(
            recording=ident,
            mode=mode,
            cpu=cfg["cpu"],
            setup=setup,
            rows=rows,
            memory_before=initial_memory,
            memory_end=resources(),
            source_sha256=_sha(work / "input-lock.json"),
            resident_sha256=_sha(work / ident / "resident-lock.json"),
        )
    write(work / ident / f"{mode}.json.gz", gzip.compress(encoded(payload), mtime=0))


def execute(work):
    lock = whole_iq.read(work / "input-lock.json")
    measured = work / "measured-sources"
    if not measured.exists():
        for source in (Path(verifier_integration.__file__), BRIDGE, Path(__file__)):
            write(measured / source.name, source.read_bytes())

    def launch(ident, phase, mode=None):
        cfg = lock["cases"][ident]
        args = [*([mode] if mode is not None else [])]
        subprocess.run(
            [
                "taskset",
                "-c",
                str(cfg["cpu"]),
                original.PYTHON,
                "-B",
                "-m",
                __spec__.name,
                phase,
                work,
                ident,
                *args,
            ],
            check=True,
            timeout=240,
            env=os.environ | THREAD_ENV | {"PYTHONPATH": f"{cfg['root']}:{ROOT}"},
        )

    def on_cpu(ids):
        for ident in ids:
            if not (work / ident / "resident-lock.json").exists():
                launch(ident, "stage")
            offset = tuple(CASES).index(ident)
            for mode in MODES[offset:] + MODES[:offset]:
                if not (work / ident / f"{mode}.json.gz").exists():
                    launch(ident, "worker", mode)

    by_cpu = {
        cpu: tuple(ident for ident, assigned in CASES.items() if cpu == assigned)
        for cpu in set(CASES.values())
    }
    with ThreadPoolExecutor(max_workers=len(by_cpu)) as executor:
        tuple(executor.map(on_cpu, by_cpu.values()))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "execute", "stage", "worker"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("case", nargs="?", choices=CASES)
    parser.add_argument("mode", nargs="?", choices=MODES)
    args = parser.parse_args()
    if args.action == "freeze":
        freeze(args.work)
    elif args.action == "execute":
        execute(args.work)
    elif args.action == "stage":
        stage(args.work, args.case)
    else:
        worker(args.work, args.case, args.mode)
