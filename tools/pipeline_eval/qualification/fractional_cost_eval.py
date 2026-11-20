"""Pair complete typed detectors with and without grouped epoch correlation."""

import argparse
import json
import os
import subprocess
import sys
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path

import numpy as np

from ..__main__ import encoded, local_output, save_json, write
from ..variants import iq_stream
from . import fractional_cost_build as build
from . import native_hotpath_eval as native
from .fifth_arm import check, science
from .full_v5_check import _from_native, _load_case, _sha

CASES = {"DS26-0197": 20, "DS29-0316": 21}
ROLES = ("typed", "grouped")
MODES = ("stock", "fifth")
MODULE = "tools.pipeline_eval.qualification.fractional_cost_eval"


def freeze(work):
    receipt = work / "build-v2/build.json"
    base = native.build.REPORT
    prior = json.loads((base / "result-lock.json").read_bytes())["files"]
    prior_input = json.loads(
        check(base / "source-lock.json", prior["source-lock.json"]).read_bytes()
    )
    iq_stream.MAX_CHUNK_PREFIX = 56 * iq_stream.MIB
    roster = {}
    for ident in CASES:
        case = _load_case(ident)
        roster[ident] = rows = []
        for segment in (2, 7):
            rows.extend(native._freeze_block(work, case, ident, segment))
        old = prior_input["roster"][ident]
        if any(
            (a["segment"], a["sequence"]) == (b["segment"], b["sequence"])
            for a in rows
            for b in old
        ):
            raise ValueError("held block overlaps the prior typed study")
    for edge in ("lower", "upper"):
        for control in ("strong", "noise", "zero"):
            if control == "zero":
                sample, target = np.zeros((200000, 2, 2), dtype="<i2"), {}
            else:
                sample, target = native.differential_pilot_eval.synthetic(edge, control)
            filename = f"{edge}-{control}.ci16"
            write(work / filename, sample.tobytes())
            lock = next(x for x in prior_input["roster"][edge] if x["file"] == filename)
            check(work / filename, lock["iq_sha256"])
            roster.setdefault(edge, []).append(lock | {"target": target})
    files = (
        Path(__file__),
        Path(native.__file__),
        Path(build.__file__),
        build.REPORT / "PROTOCOL.md",
        receipt,
        base / "source-lock.json",
    )
    save_json(
        work / "input-lock.json",
        dict(
            files={str(p): _sha(p) for p in files},
            cases=CASES,
            roster=roster,
        ),
    )


def worker(work, role, edge):
    release = work / "build-v2"
    receipt = json.loads((release / "build.json").read_bytes())
    root = release / role
    for name, digest in receipt["pair"][role].items():
        check(root / name, digest)
    with ExitStack() as stack:
        ctx = native.NativeCall(stack, root / native.build.LIBRARY, edge)
        path = str(root / native.build.DETECTOR)
        maps = Path("/proc/self/maps").read_text()
        if path not in maps or any(
            str(release / r / native.build.DETECTOR) in maps for r in ROLES if r != role
        ):
            raise ValueError("worker library map does not match its sealed role")
        print(json.dumps(dict(setup=ctx.setup, peak_kib=native.memory(), library=path)), flush=True)
        last = None
        for line in sys.stdin:
            fixture, mode = json.loads(line)
            if fixture != last:
                file = check(work / fixture["file"], fixture["iq_sha256"])
                sample = np.fromfile(file, dtype="<i2").reshape(200000, 2, 2)
                last = fixture
            rows, hints, trace, timing = ctx.measure(sample, mode)
            for name in ("proposal", "coarse", "fine_fft", "fractional_epoch", "glrt"):
                timing[f"{name}_cpu_ms"] = sum(r["timings_ms"][name] for r in rows)
            clean = science(rows)
            timing_input = native.clock()
            payload = encoded(clean)
            native.timed(timing, "json", native.millis(timing_input))
            gates = [
                [
                    c
                    for i, candidate in enumerate(r["candidates"])
                    if (c := _from_native(i, candidate)) and c["passed_fractional_margin_gate"]
                ]
                for r in rows
            ]
            grid_calls = [
                [c["refined_epoch"], c["acquired_cfo_hz"]]
                for r in rows
                for c in r["candidates"]
                if c["fractional_epoch"]["status"] != "not_evaluated"
            ]
            print(
                json.dumps(
                    dict(
                        sha256=sha256(payload).hexdigest(),
                        hints=hints,
                        trace=trace,
                        timing=timing,
                        gates=gates,
                        candidate_counts=[len(r["candidates"]) for r in clean],
                        grid_calls=grid_calls,
                        peak_kib=native.memory(),
                    )
                ),
                flush=True,
            )


@contextmanager
def start(work, role, edge):
    args = [sys.executable, "-m", MODULE, "worker", str(work), role, edge]
    env = os.environ | {
        name: "1" for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    }
    with subprocess.Popen(
        args, stdin=subprocess.PIPE, stdout=subprocess.PIPE, env=env, text=True, bufsize=1
    ) as port:
        try:
            first = port.stdout.readline()
            if not first:
                raise ValueError(f"missing process start from {role}")
            yield port, json.loads(first)
        finally:
            port.stdin.close()
            try:
                port.wait(timeout=5)
            except subprocess.TimeoutExpired:
                port.kill()
                port.wait()


def validate(pair):
    a, b = (pair[key] for key in ROLES)
    return all(a[k] == b[k] for k in ("sha256", "hints", "trace", "gates"))


def run(work, ident, smoke=False):
    lock = work / "input-lock.json"
    config = json.loads(lock.read_bytes())
    for path, digest in config["files"].items():
        check(Path(path), digest)
    if os.sched_getaffinity(0) != {CASES[ident]}:
        raise ValueError("the pair must run on its fixed single host core")
    real = [f for f in config["roster"][ident] if f["status"] == "valid"]
    edge = real[0]["edge"]
    if any(f["edge"] != edge for f in real):
        raise ValueError("recording changes RF edge")
    if smoke:
        real = real[:1]
    rows = []
    with ExitStack() as stack:
        workers = {r: stack.enter_context(start(work, r, edge)) for r in ROLES}
        for role in ROLES:
            for mode in MODES:
                native.call(workers[role][0], real[0], mode)
        for i, fixture in enumerate([*real, *config["roster"][edge]]):
            genuine = fixture["kind"] == "genuine"
            schedule = MODES if genuine else native.MODES
            row = {}
            for mode in schedule:
                row[mode] = reps = []
                for rep in range(1 if smoke else 3):
                    order = ROLES if (i + rep) % 2 == 0 else ROLES[::-1]
                    pair = {r: native.call(workers[r][0], fixture, mode) for r in order}
                    if not validate(pair):
                        save_json(
                            work / f"failure-{ident}.json",
                            dict(fixture=fixture, mode=mode, pair=pair),
                        )
                        raise ValueError(
                            f"non-clock row or support mismatch: {fixture['name']}/{mode}"
                        )
                    reps.append(pair)
            if not genuine and any(
                p["typed"]["sha256"] != q["typed"]["sha256"]
                for p, q in zip(row["stock"], row["absent"], strict=True)
            ):
                raise ValueError("absent hint differs from stock")
            rows.append(dict(fixture=fixture, modes=row))
            if i % 12 == 0:
                print(ident, i, fixture["name"], flush=True)
                save_json(work / f"{ident}-progress.json", rows)
    save_json(
        work / f"{ident}-{'smoke' if smoke else 'results'}.json",
        dict(
            core=CASES[ident],
            lock_sha256=_sha(lock),
            rows=rows,
            workers={r: v for r, (_, v) in workers.items()},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("freeze", "worker", "smoke", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("subject", nargs="?")
    parser.add_argument("edge", nargs="?")
    args = parser.parse_args()
    if args.mode == "freeze":
        freeze(args.work)
    elif args.mode == "worker":
        worker(args.work, args.subject, args.edge)
    else:
        run(args.work, args.subject, args.mode == "smoke")
