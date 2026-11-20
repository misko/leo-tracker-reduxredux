"""Compare paired Python and FFTW differential scouting on sealed saved and planted IQ."""

import argparse
import gzip
import json
import os
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter_ns, process_time_ns

import numpy as np

from ..__main__ import ROOT, encoded, save_json, write
from ..variants import differential_pilot as reference
from ..variants import iq_stream
from ..variants.differential_runtime import DifferentialCall
from ..variants.differential_runtime_fft import SOURCE, FftScout
from . import differential_pilot_eval as fixtures
from . import differential_runtime as release
from . import hinted_glrt_trial as trial
from .full_v5_check import _load_case, _sha

REPORT = fixtures.SCREEN / "acquisition-frontier/differential-runtime"
FIXTURES = fixtures.REPORT
LIBRARIES = Path("/srv/bulk/leo-dev/receiver-screening-20261119/differential-runtime/release")
BUILD = fixtures.oracle_start.ABI


def bindings():
    added = [
        Path(__file__),
        SOURCE,
        SOURCE.with_suffix(".py"),
        Path(fixtures.__file__),
        Path(trial.__file__),
        Path(iq_stream.__file__),
        REPORT / "PROTOCOL.md",
        BUILD,
        FIXTURES / "input-lock.json.gz",
        FIXTURES / "confirmation-lock.json",
    ]
    return {**release.source_identity(), **{str(p.relative_to(ROOT)): _sha(p) for p in added}}


def plan(work):
    build = json.loads(BUILD.read_bytes())
    libraries = {
        "stock": Path(build["paths"]["stock"]),
        "hinted": LIBRARIES / "libleo-adaptive-detector.so",
    }
    if {name: _sha(path) for name, path in libraries.items()} != build["library_sha256"]:
        raise ValueError("detector library changed")
    libraries["fftw"] = LIBRARIES / "libdifferential-scout.so"
    identity = dict(
        sources=bindings(),
        libraries={
            name: {"path": str(path), "sha256": _sha(path)} for name, path in libraries.items()
        },
        numpy=np.__version__,
        cpus=sorted(os.sched_getaffinity(0)),
        synthetic=list(fixtures.CONTROLS),
    )
    lock = work / "plan.json"
    if lock.exists() and json.loads(lock.read_bytes()) != identity:
        raise ValueError("comparison identity differs from the pre-run plan")
    if not lock.exists():
        save_json(lock, identity)
    return libraries


def memory():
    fields = dict(
        (line.split(":", 1)[0], int(line.split()[1]))
        for line in Path("/proc/self/status").read_text().splitlines()
        if line.startswith(("VmRSS:", "VmHWM:", "RssAnon:", "RssFile:"))
    )
    return {**fields, "ru_maxrss": getrusage(RUSAGE_SELF).ru_maxrss}


def timing(call):
    cpu, wall = process_time_ns(), perf_counter_ns()
    result = call()
    return result, dict(cpu_ns=process_time_ns() - cpu, wall_ns=perf_counter_ns() - wall)


def hints(proposals):
    return tuple(centers[0] if centers else None for centers, _ in proposals)


def compare(samples, edge, name, direct, python, compiled, fft, i):
    direct_scout = reference.scout(samples, edge)
    direct_payload, direct_trace = direct(samples, hints(direct_scout))
    measures, values = {"python": [], "fftw": []}, {}
    for repeat in range(3):
        order = [("python", python), ("fftw", compiled)]
        if (repeat + i) % 2:
            order.reverse()
        for mode, call in order:
            payload, proposals, trace, elapsed = call(samples)
            result = (payload, proposals, trace)
            if mode in values and values[mode] != result:
                raise ValueError("repeat changed payload or proposals")
            measures[mode].append(elapsed)
            values[mode] = result

    if values["python"] != (direct_payload, direct_scout, direct_trace):
        raise ValueError("opt-in route differs from direct exact scorer and hint ABI")
    compiled_payload, compiled_scout, compiled_trace = values["fftw"]
    exact_surface, compiled_surface = reference.surface(samples, edge), fft.surface(samples)
    error = np.abs(exact_surface - compiled_surface)
    return dict(
        item=name,
        edge=edge,
        input_sha256=sha256(samples.tobytes()).hexdigest(),
        timing=measures,
        full_ranks_match=[a[0] == b[0] for a, b in zip(direct_scout, compiled_scout, strict=True)],
        top_ranks_match=[
            a == b for a, b in zip(hints(direct_scout), hints(compiled_scout), strict=True)
        ],
        surf_relative_linf=(
            error.max(axis=1) / np.maximum(1, np.abs(exact_surface).max(axis=1))
        ).tolist(),
        python_proposals=direct_scout,
        fftw_proposals=compiled_scout,
        fftw_native_match=encoded(direct_payload) == encoded(compiled_payload),
        fftw_trace_match=direct_trace == compiled_trace,
        python_native_sha256=sha256(encoded(direct_payload)).hexdigest(),
        fftw_native_sha256=sha256(encoded(compiled_payload)).hexdigest(),
        trace=direct_trace,
    )


def locked_visits():
    primary = json.loads(gzip.decompress((FIXTURES / "input-lock.json.gz").read_bytes()))
    confirmation = json.loads((FIXTURES / "confirmation-lock.json").read_bytes())
    if len(primary["cases"]) != 4 or len(confirmation["cases"]) != 4:
        raise ValueError("incomplete independent raw visit rosters")
    for scope, roster in (("primary", primary["cases"]), ("confirmation", confirmation["cases"])):
        for ident, visits in roster.items():
            for row in visits:
                yield scope, ident, row


def run(work, libraries):
    report_rows = []
    before = memory()
    for edge in ("lower", "upper"):
        with ExitStack() as stack:
            contexts = [trial.bound(stack, libraries, edge)[1] for _ in range(3)]
            direct, python, compiled = contexts
            fft = stack.enter_context(FftScout(libraries["fftw"], edge))
            python = DifferentialCall(python.context, edge)
            compiled = DifferentialCall(compiled.context, edge, scout=fft)
            for label in fixtures.CONTROLS:
                samples, plant = fixtures.synthetic(edge, label)
                result = compare(
                    samples, edge, label, direct, python, compiled, fft, len(report_rows)
                )
                report_rows.append(dict(result, cohort="synthetic", plant=plant))
            for scope, ident, row in locked_visits():
                if row["archive_probe"]["edge"] != edge:
                    continue
                tag = f"{ident}:{row['visit']}"
                try:
                    window = trial.load_selected(_load_case(ident), row)
                except iq_stream.IQReadError as error:
                    report_rows.append(
                        dict(item=tag, cohort=scope, edge=edge, unavailable=str(error))
                    )
                    continue
                result = compare(
                    window.samples, edge, tag, direct, python, compiled, fft, len(report_rows)
                )
                report_rows.append(
                    dict(result, cohort=scope, case=ident, visit=row["visit"], kind=row["kind"])
                )
                print(tag, result["top_ranks_match"], result["fftw_native_match"], flush=True)
    write(work / "paired.json.gz", gzip.compress(encoded(report_rows), mtime=0))
    save_json(work / "paired-runtime.json", dict(start=before, end=memory(), rows=len(report_rows)))


def resource_probe(work, libraries, mode):
    samples, _ = fixtures.synthetic("lower", "one-frame")
    initial = memory()
    with ExitStack() as stack:
        _, hinted = trial.bound(stack, libraries, "lower")
        selected = reference.scout
        if mode == "fftw":
            selected = stack.enter_context(FftScout(libraries["fftw"], "lower"))
        call = DifferentialCall(hinted.context, "lower", scout=selected)
        timings = [call(samples)[3] for _ in range(20)]
        final = memory()
    save_json(work / f"resource-{mode}.json", dict(start=initial, end=final, timings=timings))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "paired", "python", "fftw"))
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    if len(os.sched_getaffinity(0)) != 1:
        parser.error("use a single pinned host CPU")
    args.work.mkdir(parents=True, exist_ok=True)
    libraries = plan(args.work)
    if args.action == "paired":
        run(args.work, libraries)
    elif args.action in ("python", "fftw"):
        resource_probe(args.work, libraries, args.action)


if __name__ == "__main__":
    main()
