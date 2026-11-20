"""Qualify the exact shared-library port used by the complete IQ replay."""

import argparse
import json
import os
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..variants import center_union
from ..variants.differential_runtime_fft import FftScout
from . import fractional_cost_build as build
from . import fractional_cost_eval as evaluate
from .fifth_arm import check, science
from .full_v5_check import _from_native, _sha
from .wide_regional_eval import templates

ENTRY = center_union.ENTRY


def read(path):
    return json.loads(path.read_bytes())


def bind(work):
    built = work / "build-v2"
    receipt = read(built / "build.json")
    libraries = {n: check(built / "whole" / n, v) for n, v in receipt["whole"].items()}
    control = read(build.typed.REPORT / "build.json")
    original = check(build.typed.UNION, control["original_union_sha256"])
    return dict(
        candidate=libraries["libleo-adaptive-detector.so"],
        scout=libraries[build.SCOUT.name],
        baseline=original,
    )


def scores(rows):
    return [
        [
            c
            for i, candidate in enumerate(lane["candidates"])
            if (c := _from_native(i, candidate)) and c["passed_fractional_margin_gate"]
        ]
        for lane in rows
    ]


def run(work, ident):
    from leo.analysis.starlink.native_short_window import NativeShortWindow

    if os.sched_getaffinity(0) != {evaluate.CASES[ident]}:
        raise ValueError("pin the direct ABI witness to the designated core")
    source = work / "input-lock.json"
    lock = read(source)
    for path, digest in lock["files"].items():
        check(Path(path), digest)
    selected = [r for r in lock["roster"][ident] if r["status"] == "valid" and r["sequence"] < 4]
    edge = selected[0]["edge"]
    paths = bind(work)
    exact, control = templates(10_000_000, edge)
    rows = []
    with ExitStack() as stack:
        scout = stack.enter_context(FftScout(paths["scout"], edge))
        calls = {}
        for role in ("baseline", "candidate"):
            native = stack.enter_context(
                NativeShortWindow(
                    str(paths[role]),
                    exact,
                    control,
                    sample_rate_hz=10_000_000,
                    fractional_epoch=True,
                )
            )
            calls[role] = center_union.DifferentialUnionCall(native, edge, scout=scout)
        for fixture in selected + lock["roster"][edge]:
            file = check(work / fixture["file"], fixture["iq_sha256"])
            sample = np.fromfile(file, dtype="<i2").reshape(200000, 2, 2)
            data = {}
            for role, call in calls.items():
                result, proposed, support, clock = call(sample, timings=True)
                prefix = science(result["rows"])
                absent, trace = call.hinted(sample, (None, None))
                if prefix == [] or len(absent["rows"]) != 2:
                    raise ValueError("full direct ABI did not return both rows")
                data[role] = dict(
                    payload_sha256=evaluate.sha256(encoded(prefix)).hexdigest(),
                    proposals=proposed,
                    support=support,
                    gates=scores(prefix),
                    count=[len(r["candidates"]) for r in prefix],
                    absent_sha256=evaluate.sha256(encoded(absent["rows"])).hexdigest(),
                    absent=trace,
                )
            if encoded(data["baseline"]) != encoded(data["candidate"]):
                raise ValueError(f"direct center-union public parity failed: {fixture['name']}")
            positive = data["candidate"]["gates"]
            if fixture["kind"] in ("noise", "zero") and any(positive):
                raise ValueError("negative direct control produced a positive gate")
            if fixture["kind"] == "strong" and not all(positive):
                raise ValueError("direct signed pilot missed a receiver")
            rows.append(dict(fixture=fixture, **data["candidate"]))
    save_json(
        work / f"direct-{edge}.json",
        dict(
            case=ident,
            edge=edge,
            rows=rows,
            input_lock_sha256=_sha(source),
            paths={k: {"path": str(v), "sha256": _sha(v)} for k, v in paths.items()},
            worker_sha256=_sha(Path(__file__)),
            core=evaluate.CASES[ident],
        ),
    )


def seal(work):
    output = build.REPORT
    paths = bind(work)
    lock = work / "input-lock.json"
    files = {}
    for name in ("input-lock.json", "direct-lower.json", "direct-upper.json"):
        path = work / name
        if name != "input-lock.json":
            r = read(path)
            if (
                r["input_lock_sha256"] != _sha(lock)
                or len(r["rows"]) != 11
                or any(r["paths"][k]["sha256"] != _sha(p) for k, p in paths.items())
            ):
                raise ValueError("direct proof incomplete or bound to different detector")
        write(output / name, path.read_bytes())
        files[name] = _sha(output / name)
    sources = (
        Path(__file__),
        Path(evaluate.__file__),
        Path(build.__file__),
        build.HEADER,
        Path(center_union.__file__),
        Path(evaluate.native.__file__),
    )
    save_json(
        output / "whole-feature-gate.json",
        dict(
            entry=ENTRY,
            baseline_sha256=_sha(paths["baseline"]),
            passed=True,
            exact_edges=["lower", "upper"],
            candidate_rows_exact=True,
            support_and_gates_exact=True,
            candidate=dict(path=str(paths["candidate"]), sha256=_sha(paths["candidate"])),
            scout=dict(path=str(paths["scout"]), sha256=_sha(paths["scout"])),
            files=files,
            sources={str(p.relative_to(ROOT)): _sha(p) for p in sources},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("run", "seal"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("case", nargs="?")
    args = parser.parse_args()
    if args.mode == "run":
        run(args.work, args.case)
    else:
        seal(args.work)
