"""Bounded paired discovery benchmark over fixed public inputs; no numerical fitting."""

import argparse
import ast
import hashlib
import importlib.util
import json
import random
import signal
import sys
import textwrap
import time
from pathlib import Path

from stage_algo02_runtime import verify


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adapt(original, current):
    """Apply only the cache to the older installed store, preserving every other API."""
    tree = ast.parse(current)
    helper = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_discovery_file_identity")
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "FastGraphPositionStore")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_discovery_digest")
    limit = next(n for n in tree.body if isinstance(n, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == "_DISCOVERY_DIGEST_LIMIT"
                         for t in n.targets))
    fragments = {name: ast.get_source_segment(current, node)
                 for name, node in (("helper", helper), ("method", method), ("limit", limit))}
    # ast strips indentation only from the first line; restore it before dedenting.
    fragments["method"] = textwrap.dedent("    " + fragments["method"])
    replacements = {
        "from contextlib import contextmanager":
            "from collections import OrderedDict\nfrom contextlib import contextmanager",
        "class FastGraphPositionStore:":
            fragments["limit"] + "\n\n\n" + fragments["helper"]
            + "\n\n\nclass FastGraphPositionStore:",
        '        self.namespace = self.root / "fast-scan-graph-position-v1" / MODEL_VERSION':
            '        self.namespace = self.root / "fast-scan-graph-position-v1" / MODEL_VERSION\n'
            '        self._discovery_digests = OrderedDict()',
        "            digest = sha(path)": "            digest = self._discovery_digest(path)",
        "    def status(self, identifier):":
            textwrap.indent(fragments["method"], "    ")
            + "\n\n    def status(self, identifier):",
    }
    if "_discovery_digests" in original:
        raise ValueError("Already modified baseline")
    for before, after in replacements.items():
        if original.count(before) != 1:
            raise ValueError("Unexpected installed store layout: " + before)
        original = original.replace(before, after)
    compile(original, "discovery-prototype", "exec")
    return original


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def measure(store, expected, counters):
    counters.clear()
    began, cpu = time.perf_counter(), time.process_time()
    jobs = list(store.inputs())
    rows = []
    for job in jobs:
        state = store.status(job["job_id"])
        rows.append(dict(job_id=job["job_id"], input_sha256=job["input_sha256"],
                         run_id=job["run_id"], state=None if state is None else state["state"]))
    result = dict(wall_seconds=time.perf_counter()-began, cpu_seconds=time.process_time()-cpu,
                  input_hash_calls=len(counters), input_hashed_bytes=sum(counters))
    if rows != expected:
        raise ValueError("Discovery identities, hashes, ordering or statuses changed")
    return result


def snapshot(args):
    runtime, output = args.runtime.resolve(strict=True), args.output.resolve()
    verify(runtime, args.pin)
    if not output.is_relative_to("/srv/bulk/leo/research") or output.exists():
        raise ValueError("New private research output required")
    output.mkdir(parents=True)
    sys.path.insert(0, str(runtime / "src"))
    source = runtime / "src/leo/storage/fast_graph_position.py"
    store = module(source, "original_discovery").FastGraphPositionStore(args.bulk_root)
    paths = store.inputs_port.exported_tracking_inputs()
    count = len(paths) if args.limit == 0 else min(args.limit, len(paths))
    selected = sorted(random.Random(args.seed).sample(range(len(paths)), count))
    fixed = tuple(paths[i] for i in selected)
    store.inputs_port.exported_tracking_inputs = lambda: fixed
    began, cpu = time.perf_counter(), time.process_time()
    jobs = list(store.inputs())
    rows = []
    for job in jobs:
        state = store.status(job["job_id"])
        rows.append(dict(job_id=job["job_id"], input_sha256=job["input_sha256"],
                         run_id=job["run_id"], state=None if state is None else state["state"]))
    result = dict(runtime=str(runtime), runtime_manifest_sha256=args.pin,
                  seed=args.seed, public_inventory_count=len(paths),
                  selected=[dict(path=str(p), size=p.stat().st_size,
                                 mtime_ns=p.stat().st_mtime_ns) for p in fixed],
                  measurements=[dict(wall_seconds=time.perf_counter()-began,
                                     cpu_seconds=time.process_time()-cpu, jobs=rows)],
                  source_module_sha256=digest(source), maximum_seconds=120,
                  production_modified=False, scope="Frozen public discovery inventory")
    (output / "fixture.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(cases=len(fixed), bytes=sum(r["size"] for r in result["selected"]),
                          seconds=result["measurements"][0]["wall_seconds"])))


def run(args):
    output, runtime = args.output.resolve(), args.runtime.resolve(strict=True)
    if not output.is_relative_to("/srv/bulk/leo/research") or output.exists():
        raise ValueError("New private research output required")
    verify(runtime, args.pin)
    output.mkdir(parents=True)
    relative = "src/leo/storage/fast_graph_position.py"
    original = runtime / relative
    current = args.checkout.resolve(strict=True) / relative
    installed = args.candidate_runtime.resolve(strict=True) if args.candidate_runtime else None
    if installed:
        verify(installed, args.candidate_pin)
        candidate = installed / relative
    else:
        candidate = output / "candidate_store.py"
        candidate.write_text(adapt(original.read_text(), current.read_text()))
    sys.path.insert(0, str(runtime / "src"))
    modules = [module(original, "original_discovery"), module(candidate, "candidate_discovery")]
    stores = [m.FastGraphPositionStore(args.bulk_root) for m in modules]
    fixture = json.loads(args.fixture.read_text())
    fixed = tuple(Path(r["path"]) for r in fixture["selected"])
    public = set(stores[0].inputs_port.exported_tracking_inputs())
    if not fixed or len(set(fixed)) != len(fixed) or not set(fixed) <= public:
        raise ValueError("Fixed inputs must belong to the public input port")
    expected = fixture["measurements"][0]["jobs"]
    for path, row in zip(fixed, expected, strict=True):
        if "sha256:" + digest(path) != row["input_sha256"]:
            raise ValueError("Frozen public input changed")
    counters = [[], []]
    for index, (store, mod) in enumerate(zip(stores, modules, strict=True)):
        store.inputs_port.exported_tracking_inputs = lambda: fixed
        original_sha = mod.sha

        def counted(path, sha=original_sha, calls=counters[index]):
            calls.append(path.stat().st_size)
            return sha(path)

        mod.sha = counted
    cold = [measure(s, expected, c) for s, c in zip(stores, counters, strict=True)]
    trials = []
    for repeat in range(args.repeats):
        for side in ((0, 1) if repeat % 2 == 0 else (1, 0)):
            trials.append(dict(repeat=repeat, variant=("baseline", "candidate")[side],
                               **measure(stores[side], expected, counters[side])))
    for path, row in zip(fixed, expected, strict=True):
        if "sha256:" + digest(path) != row["input_sha256"]:
            raise ValueError("Frozen public input changed during measurement")
    verify(runtime, args.pin)
    if installed:
        verify(installed, args.candidate_pin)
    result = dict(exact=True, cases=len(fixed), seed=fixture["seed"], cold=cold, trials=trials,
                  original_source_sha256=digest(original),
                  candidate_source_sha256=digest(candidate),
                  current_source_sha256=digest(current), fixture_sha256=digest(args.fixture),
                  benchmark_script_sha256=digest(Path(__file__)),
                  runtime=str(runtime), runtime_manifest_sha256=args.pin,
                  candidate_runtime=str(installed) if installed else None,
                  candidate_runtime_manifest_sha256=args.candidate_pin if installed else None,
                  candidate_source=str(candidate), maximum_seconds=120,
                  changed_states_hidden=False, production_modified=False,
                  scope="fixed public input discovery only; no fresh numerical inference")
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime", "checkout", "bulk-root", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--fixture", type=Path)
    parser.add_argument("--candidate-runtime", type=Path)
    parser.add_argument("--candidate-pin")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--limit", type=int, choices=range(0, 4097), default=32,
                        help="Snapshot size; zero selects the complete public inventory")
    parser.add_argument("--seed", type=int, default=20261103)
    parser.add_argument("--pin", required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 11), default=5)
    args = parser.parse_args()
    if not args.snapshot and args.fixture is None:
        parser.error("--fixture is required for a paired measurement")
    if bool(args.candidate_runtime) != bool(args.candidate_pin):
        parser.error("Both --candidate-runtime and --candidate-pin are required together")

    def deadline(*_):
        raise TimeoutError("120-second discovery benchmark bound exceeded")

    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(120)
    (snapshot if args.snapshot else run)(args)
