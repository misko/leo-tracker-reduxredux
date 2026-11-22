"""Audit exact initial prefixes and nominal-mode reuse on a released India input."""

import argparse
import json
import os
import pickle
import runpy
import struct
import subprocess
from collections import Counter, defaultdict
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import process_time_ns
from unittest.mock import patch

import numpy as np


SOURCE = Path(__file__).resolve()
TRANSFER = SOURCE.with_name("covariance_transfer_trial.py")
TRACE = SOURCE.with_name("portable_south_solver_trace.py")
OVERLAY = SOURCE.parents[3] / "tools/pipeline_eval/variants/algo08_nominal_angular_bank.py"
CASE = "02213f589249d02be64805a5d2ea12ef"
NATIVE = "5bfc82a689df80b482a2dae985642403fb4615c1fac34550e490884fcc96d569"


def numeric_digest(args, kwargs):
    digest = sha256()

    def field(blob):
        digest.update(len(blob).to_bytes(8, "little"))
        digest.update(blob)

    def value(v):
        if isinstance(v, np.ndarray) and not v.dtype.hasobject:
            field(b"array")
            field(pickle.dumps((v.dtype.str, v.shape), protocol=5))
            field(v.tobytes(order="C"))
        elif type(v) is float:
            field(b"float")
            field(struct.pack("=d", v))
        elif v is None or type(v) in (int, bool):
            field(type(v).__name__.encode())
            field(str(v).encode())
        else:
            raise TypeError("Unknown numerical solver operand")

    field(str(len(args)).encode())
    for operand in args:
        value(operand)
    for key, item in sorted(kwargs.items()):
        field(key.encode())
        value(item)
    return digest.digest()


@contextmanager
def profile_prefix(port):
    from leo.analysis.localization_v3 import conservative_recovery, position
    from tools.pipeline_eval.variants import v5_core

    calls = defaultdict(set)
    result = Counter()
    group, branch = None, 0

    def bind(operation, target):
        def observed(*args, **kwargs):
            nonlocal group, branch
            saved = group
            if target == "branch":
                branch += 1
                group = f"branch_{branch}"
            else:
                group = target
            label = group
            start = process_time_ns()
            try:
                return operation(*args, **kwargs)
            finally:
                result[f"{label}_instrumented_cpu_ns"] += process_time_ns() - start
                group = saved
        return observed

    method = port.NativeBound.__call__

    def compute(self, *args, **kwargs):
        if group is None:
            return method(self, *args, **kwargs)
        token = (self, numeric_digest(args, kwargs))
        seen = calls[token]
        label = None
        if group.startswith("branch_"):
            if any(other.startswith("branch_") and other != group for other in seen):
                label = "distinct_branches"
            elif group not in seen and "ranking" in seen:
                label = "ranking_to_first_fit"
        elif group == "conservative" and any(other != group for other in seen):
            label = "initial_to_conservative"
        seen.add(group)
        start = process_time_ns()
        try:
            return method(self, *args, **kwargs)
        finally:
            elapsed = process_time_ns() - start
            result[f"{group}_native_calls"] += 1
            result[f"{group}_native_cpu_ns"] += elapsed
            if label is not None:
                result[f"{label}_hits"] += 1
                result[f"{label}_native_cpu_ns"] += elapsed

    routes = ((v5_core, "ranked_initial_nodes", "ranking"), (position, "refreshed", "branch"),
              (conservative_recovery, "conservative_recovery", "conservative"))
    with ExitStack() as stack:
        stack.enter_context(patch.object(port.NativeBound, "__call__", compute))
        for module, name, target in routes:
            stack.enter_context(patch.object(module, name, bind(getattr(module, name), target)))
        yield result


def worker(mode, site, output):
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from tools import algo08_position

    transfer, trace, variant = (runpy.run_path(str(path)) for path in (TRANSFER, TRACE, OVERLAY))
    solve = algo08_position.solve
    notes, measured, science = {}, {}, {}

    def collect(*args, **kwargs):
        with (trace["traced"](notes, False), profile_prefix(algo08_position) as profile,
              variant["nominal_angular_bank"](enabled=mode == "reuse") as cache):
            decision, packet, policy = solve(*args, **kwargs)
        measured.update(prefix=dict(profile), angular_bank=dict(cache))
        if packet is not None:
            for key in ("position_path", "position_grid", "objective_replay"):
                science[key] = canonical_digest({k: v for k, v in packet[key].items()
                                                 if k not in ("binding", "elapsed_seconds")})
        return decision, packet, policy

    with TemporaryDirectory() as temp, patch.object(algo08_position, "solve", collect):
        final = Path(temp) / "solve.json"
        transfer["worker"](site / "native.json", site / "tle", site / "matched-tile.json", final)
        result = json.loads(final.read_bytes())
    notes.pop("published_points", None)
    with output.open("x") as target:
        json.dump(dict(result=result, science=science, stages=notes, measurements=measured),
                  target, default=_json_value, allow_nan=False)


def run(root, output):
    from tools.pipeline_eval.qualification.paired_publication import archive_identity

    release = runpy.run_path(str(TRANSFER))["RELEASE"]
    if Path("/opt/leo-algo08/current").resolve() != release:
        raise ValueError("Expected the released installed solver")
    site = root / CASE
    plan, = [r for r in json.loads((root / "plan.json").read_bytes())
             if r["case"] == CASE and r["mode"] == "matched-tile"]
    if (sha256((site / "native.json").read_bytes()).hexdigest() != NATIVE
            or plan["document_sha256"] != NATIVE
            or json.loads((site / "matched-tile.json").read_bytes()) != plan["offer"]):
        raise ValueError("Expected the pre-existing matched India inputs")
    archive = archive_identity(site / "tle")
    original = json.loads((site / "matched-tile-installed.json").read_bytes())
    env = dict(os.environ, PYTHONPATH=f"{release / 'src'}:{release}", OPENBLAS_NUM_THREADS="1",
               MKL_NUM_THREADS="1", OMP_NUM_THREADS="1")
    for key in ("ALGO08_EVALUATION_LATITUDE", "ALGO08_EVALUATION_LONGITUDE", "ALGO08_REGION_FILE",
                "ALGO08_EXPERIMENT_CONFIG"):
        env.pop(key, None)
    results = {}
    with TemporaryDirectory() as temp:
        for mode in ("stock", "reuse"):
            trace = Path(temp) / f"{mode}.json"
            subprocess.run([str(release / "venv/bin/python"), "-BPs", str(SOURCE), "worker", mode,
                            str(site), str(trace)], check=True, env=env, timeout=45)
            results[mode] = json.loads(trace.read_bytes())
    if archive_identity(site / "tle") != archive:
        raise ValueError("Archived TLE objects changed during the comparison")
    keys = ("status", "reason", "arms", "associated", "owners", "orbit_policy")
    published = {mode: all(result["result"][key] == original[key] for key in keys)
                 for mode, result in results.items()}
    exact = {key: results["stock"][key] == results["reuse"][key] for key in ("science", "stages")}
    with output.open("x") as target:
        json.dump(dict(plan=plan, archive=archive, release=release.name, published=published,
                       exact=exact, results=results, overlay_sha256=sha256(OVERLAY.read_bytes()).hexdigest()),
                  target, sort_keys=True, indent=2)
    if not all(published.values()) or not all(exact.values()):
        raise ValueError(f"Scientific results or frozen evidence differ. See {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    trial = commands.add_parser("run")
    trial.add_argument("root", type=Path)
    trial.add_argument("output", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("mode", choices=("stock", "reuse"))
    child.add_argument("site", type=Path)
    child.add_argument("output", type=Path)
    options = vars(parser.parse_args())
    {"run": run, "worker": worker}[options.pop("action")](**options)
