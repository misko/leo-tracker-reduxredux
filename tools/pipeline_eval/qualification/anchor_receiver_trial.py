"""Run the sealed same-input qualification of independent Doppler anchors."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, references, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from . import joint_orbits_inputs as joint
from . import owner_factor as owners
from . import robust_orbit_fit_trials as exact
from .fresh_scenes import _destination, _new, _read, _sandbox, _score_rows, _sha
from .full_v5_check import _load_case
from .robust_em_trials import load

ROOT = owners.ROOT
REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/anchor-receiver"
FILE = "predictions.jsonl.gz"
METHODS = ("anchor_receiver_orbits", "joint_orbits", "robust_orbit_fit")
COHORTS = {
    "first": ("DS26-0024", "DS26-0247", "DS26-0154", "DS26-0100"),
    "second": ("DS26-0229", "DS26-0313", "DS26-0299", "DS26-0106"),
}
PILOTS = {
    "DS26-0066",
    "DS26-0185",
    "DS26-0120",
    "DS26-0012",
    "DS26-0130",
    "DS26-0102",
    "DS26-0263",
    "DS26-0200",
    "DS26-0098",
    "DS26-0002",
    "DS26-0104",
    "DS26-0202",
}
CPUS = {2, 3, 6}
TIMEOUT = 45
WORKER = """
import importlib
import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import process_time

request = json.load(sys.stdin)
solver = importlib.import_module('tools.pipeline_eval.variants.' + request.pop('method'))
started = process_time()
result = solver.infer(request['observation'], request['offer'], request['catalogue'])
json.dump(dict(result=result, worker_cpu_s=process_time()-started,
               max_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def roster():
    ids, _ = corpus._selection("ds26-common127")
    frozen, _ = corpus._selection("roof16")
    excluded = set(frozen) | set(joint.CONFIRMATION) | set(owners.CASES) | set(exact.CONFIRMATION)
    eligible = {
        c
        for c in set(ids) - excluded - PILOTS
        if all(_load_case(c).get(k) for k in ("graph", "catalog", "native"))
    }
    for label, fixed in COHORTS.items():
        selected = tuple(
            sorted(
                eligible,
                key=lambda c: sha256(
                    f"anchor-identities/{label}/2026-11-19/v1:{c}".encode()
                ).digest(),
            )[:4]
        )
        if selected != fixed:
            raise ValueError("selected cohort differs from its metadata-only roster")
        eligible -= set(selected)


def sources():
    previous = _read(exact.OUTPUT / "source-lock.json")
    if previous != exact.locked_sources():
        raise ValueError("the exact control differs from its historical release")
    joint_source = ROOT / "tools/pipeline_eval/variants/joint_orbits.py"
    joint_lock = (
        ROOT / "reports/2026_11_19_receiver_screening/inference/joint-orbits/source-lock.json"
    )
    if _sha(joint_source) != _read(joint_lock)["files"][str(joint_source.relative_to(ROOT))]:
        raise ValueError("the joint control differs from its historical release")
    local = Path(__file__).parent
    paths = (
        REPORT / "PROTOCOL.md",
        Path(__file__),
        local / "full_v5_check.py",
        local / "fresh_scenes.py",
        local / "robust_em_trials.py",
        corpus.FROZEN / "provenance.json",
        joint_lock,
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        *(ROOT / "tools/pipeline_eval/variants" / f"{m}.py" for m in METHODS),
    )
    return dict(
        files={str(path.resolve().relative_to(ROOT)): _sha(path) for path in paths},
        control_dependencies=previous,
        cohorts={s: list(c) for s, c in COHORTS.items()},
    )


def _row(case, cohort, packet, bindings):
    identifier = case if cohort != "omitted" else f"{case}-omitted"
    return dict(
        id=identifier,
        capture_id=case,
        cohort=cohort,
        tile=packet["offer"],
        bindings=bindings,
        packet=packet,
        input_sha256=sha256(encoded(packet)).hexdigest(),
    )


def prepare(root, cache):
    root.mkdir(mode=0o700)
    roster()
    _new(root / "source-lock.json", sources())
    queries = []
    for label, cases in COHORTS.items():
        for index, case in enumerate(cases):
            packet, bindings = load(case, "matched-tile", cache)
            queries.append(_row(case, label, packet, bindings))
            if label == "first" and index < 3:
                heading = int.from_bytes(
                    sha256(f"anchor-absent/{case}".encode()).digest()[:4], "big"
                )
                bearing = heading / 2**32 * 6.283185307179586
                center = _destination(packet["offer"]["center"], (42, 55, 71)[index], bearing)
                tile = dict(id=f"omitted-{index}", center=center, width_km=25.0)
                queries.append(_row(case, "omitted", packet | {"offer": tile}, bindings))
    raw = gzip.compress(encoded(queries) + b"\n", mtime=0)
    (root / "queries.json.gz").write_bytes(raw)
    _new(
        root / "input-lock.json",
        dict(
            source_lock_sha256=_sha(root / "source-lock.json"),
            queries_sha256=_sha(root / "queries.json.gz"),
            cases={row["id"]: {k: v for k, v in row.items() if k != "packet"} for row in queries},
        ),
    )


def _queries(root):
    seal = _read(root / "input-lock.json")
    if (
        _sha(root / "source-lock.json") != seal["source_lock_sha256"]
        or _read(root / "source-lock.json") != sources()
        or _sha(root / "queries.json.gz") != seal["queries_sha256"]
    ):
        raise ValueError("the scheduled roster or frozen source changed")
    return json.loads(gzip.decompress((root / "queries.json.gz").read_bytes()))


def _try(row, method, cpu):
    request = encoded(row["packet"] | {"method": method})
    command = _sandbox(cpu)
    command[-1] = WORKER
    start = perf_counter()
    try:
        response = subprocess.run(
            command,
            input=request,
            capture_output=True,
            check=True,
            timeout=TIMEOUT,
        )
        outcome = json.loads(response.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        message = (err.stderr or b"").decode(errors="replace")[-1200:] or str(err)
        result = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=message,
            boundary="Prepared GLRT Doppler tracks",
            metrics={},
            arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
        )
        outcome = dict(result=result, worker_cpu_s=None, max_rss_kib=None)
    wall = perf_counter() - start
    validate_result(outcome["result"])
    print(row["id"], method, outcome["result"]["status"], round(wall, 2), flush=True)
    return dict(
        **{k: v for k, v in row.items() if k not in {"packet", "bindings"}},
        **row["bindings"],
        **outcome,
        method=method,
        mode="supplied-tile",
        wall_s=wall,
    )


def predict(root):
    cpus = sorted(os.sched_getaffinity(0))
    if not cpus or not set(cpus) <= CPUS:
        raise ValueError("pin workers to assigned CPUs 2, 3 or 6")
    queries = _queries(root)

    def lane(i):
        return [_try(row, m, cpus[i]) for row in queries[i :: len(cpus)] for m in METHODS]

    with ThreadPoolExecutor(len(cpus)) as pool:
        rows = [r for group in pool.map(lane, range(len(cpus))) for r in group]
    _queries(root)
    _jsonl(root / FILE, rows)
    _new(
        root / "prediction-lock.json",
        dict(
            input_lock_sha256=_sha(root / "input-lock.json"),
            cases=[q["id"] for q in queries],
            source_lock_sha256=_sha(root / "source-lock.json"),
            files={FILE: _sha(root / FILE)},
            cpus=cpus,
        ),
    )


def _jsonl(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def _verify(root):
    seal = _read(root / "prediction-lock.json")
    inputs = _read(root / "input-lock.json")
    if (
        seal["files"][FILE] != _sha(root / FILE)
        or seal["input_lock_sha256"] != _sha(root / "input-lock.json")
        or seal["source_lock_sha256"] != _sha(root / "source-lock.json")
    ):
        raise ValueError("the prediction packet changed after sealing")
    rows = list(map(json.loads, gzip.decompress((root / FILE).read_bytes()).splitlines()))
    if len(rows) != len(seal["cases"]) * len(METHODS) or {(r["id"], r["method"]) for r in rows} != {
        (q, m) for q in seal["cases"] for m in METHODS
    }:
        raise ValueError("a paired anchor/control prediction is absent")
    for row in rows:
        source = inputs["cases"][row["id"]]
        keys = source["bindings"] | {k: source[k] for k in ("input_sha256", "tile", "capture_id")}
        if any(row[k] != v for k, v in keys.items()):
            raise ValueError("prediction does not bind a common input")
    return rows


def score(root, output):
    predictions = _verify(root)
    ids = [c for cases in COHORTS.values() for c in cases]
    truth = {r["id"]: r["truth"] for r in references("ds26-common127", ids)[1]}
    cases, labels = [], {}
    for r in predictions:
        case = r["id"]
        point = truth[r["capture_id"]]
        missing = r["cohort"] == "omitted"
        if missing and distance_km(point, r["tile"]["center"]) <= 25 / 2**0.5:
            raise ValueError("scheduled omitted offer could include the reference")
        labels[case] = dict(condition="missing" if missing else "present", latlon=point)
        metrics = r["result"]["metrics"]
        for row in _score_rows([r], labels):
            cases.append(
                dict(
                    row,
                    cohort=r["cohort"],
                    worker_cpu_s=r["worker_cpu_s"],
                    associated_observations=metrics.get("associated_observations", 0),
                    held_anchor_rms_hz=metrics.get("anchor_held_rms_hz"),
                    control_held_score=metrics.get("held_score"),
                )
            )
    grouped = []
    for method in METHODS:
        for arm in ARMS:
            for cohort in (*COHORTS, "omitted"):
                batch = [
                    r
                    for r in cases
                    if (r["method"], r["arm"], r["cohort"]) == (method, arm, cohort)
                ]
                grouped.append(
                    dict(
                        method=method,
                        arm=arm,
                        cohort=cohort,
                        attempts=len(batch),
                        publications=sum(r["published"] for r in batch),
                        within_5km=sum(
                            r["error_km"] is not None and r["error_km"] <= 5 for r in batch
                        ),
                        position=distribution(r["error_km"] for r in batch),
                        forced=distribution(r["forced_error_km"] for r in batch),
                        conditional_rms_hz=distribution(r["rf_rms_hz"] for r in batch),
                        cpu_s=distribution(r["worker_cpu_s"] for r in batch),
                    )
                )
    for name in (FILE, "prediction-lock.json", "input-lock.json", "source-lock.json"):
        write(output / name, (root / name).read_bytes())
    save_json(output / "scores.json", dict(cases=cases, labels=labels, groups=grouped))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "predict", "score"):
        sub = commands.add_parser(action)
        sub.add_argument("root", type=Path)
        if action == "prepare":
            sub.add_argument("--cache", type=Path, required=True)
        if action == "score":
            sub.add_argument("--out", type=Path, default=REPORT)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.root, args.cache)
    elif args.action == "predict":
        predict(args.root)
    else:
        score(args.root, args.out)


if __name__ == "__main__":
    main()
