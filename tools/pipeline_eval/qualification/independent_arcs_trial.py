"""Lock and run the independent native-arc receiver and matching controls."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import independent_arcs as solver
from . import paired_peaks_trial as previous
from .armijo_finish_results import pack
from .cold_input import load
from .prefix_figures import TIMING_IDS

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/streamlined/independent-arcs"
CPUS = (8, 9, 10)
CAP, DEADLINE = 100, 480
prior = previous.prior
NULL = previous.NULL
METHODS = (solver.METHOD, "paired_peaks", "peak_paths")
MATCH = ("input_sha256", "original_request_sha256", "native_sha256", "catalog_sha256", "tile")
WORKER = (
    previous.WORKER.replace(
        "from tools.pipeline_eval.variants import paired_peaks as solver",
        "from tools.pipeline_eval.variants import independent_arcs as solver, paired_peaks",
    )
    .replace("files = law, stock,", "files = law, Path(paired_peaks.__file__), stock,")
    .replace("result, trace = solver.solve", "result = solver.solve")
    .replace("result=result, trace=trace,", "result=result,")
)


def rows():
    parent = prior.archive.REPORT
    seal = prior.read(parent / "prediction-lock.json")
    prior.archive.base.secant_full._verify_files(parent, seal["files"])
    excluded = (
        {x["recording"] for x in prior.bindings()[0]} | set(previous.CONFIRMATION) | set(TIMING_IDS)
    )
    pool = [
        r
        for r in prior.read(parent / "plan.json")["cases"]
        if r["cohort"] == "roof" and r["id"] not in excluded
    ]
    reserves = sorted(
        pool, key=lambda r: prior.digest(("independent-arcs-20261119/" + r["id"]).encode())
    )[:4]
    if len(reserves) != 4:
        raise ValueError("not enough unseen roof requests")
    selected = []
    for r in reserves:
        p = r["packet"]
        selected.append(
            dict(
                id=r["id"],
                recording=r["recording"],
                cohort="confirmation",
                tile=p["offer"],
                native_sha256=p["native"]["sha256"],
                catalog_sha256=p["catalogue"]["sha256"],
                original_request_sha256=prior.digest(encoded(p)),
                cutoff=p["cutoff"],
                collected=p["catalog_timestamp"],
                shuffle=False,
                misalign=False,
            )
        )
    fixed = previous.rows()
    return [*fixed[:2], *selected, *fixed[-3:]]


def attempt(q, cpu, methods, files, digest):
    start = perf_counter()
    capture = load(q["recording"])
    if (
        capture.native_sha256,
        capture.catalog_sha256,
        capture.cutoff_utc_ns,
        capture.catalog_timestamp_ns,
    ) != (q["native_sha256"], q["catalog_sha256"], q["cutoff"], q["collected"]):
        raise ValueError("native handoff does not bind the released query")
    argv = prior.command(cpu, "peak_paths", methods["peak_paths"][0])
    argv[-1] = WORKER
    for p in files[:2]:
        argv[-4:-4] = ["--ro-bind", str(p), str(Path("/worker") / p.relative_to(ROOT))]
    payload = dict(
        capture=vars(capture) | {"catalog": capture.catalog.decode("ascii")},
        tile=q["tile"],
        shuffle=False,
    )
    try:
        result = subprocess.run(
            argv,
            input=encoded(payload | dict(misalign=q["misalign"], implementation_sha256=digest)),
            timeout=CAP,
            capture_output=True,
            check=True,
        )
        out = json.loads(result.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-3000:]
        out = {
            "result": dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=detail or str(err),
                boundary=solver.BOUNDARY,
                metrics={},
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
            )
        }
    validate_result(out["result"])
    row = dict(
        q,
        method=solver.METHOD,
        cpu=cpu,
        input_sha256=prior.digest(encoded(payload)),
        implementation_sha256=digest,
        native_elapsed_s=perf_counter() - start,
        **out,
    )
    print(
        q["id"],
        row["method"],
        out["result"]["status"],
        out["result"]["reason"],
        out["result"]["metrics"].get("selected_orbits"),
        round(row["native_elapsed_s"], 2),
        flush=True,
    )
    return row


def run(work, diagnostic_only=False):
    jobs = rows()
    algorithms = prior.sources()
    stock_files = [*algorithms["peak_paths"][0], ROOT / "tools/pipeline_eval/reference/grid.py"]
    pair_files = [Path(previous.paired.__file__), *stock_files]
    candidate = [Path(solver.__file__), *pair_files]
    pin = prior.digest(b"".join(p.read_bytes() for p in candidate))
    pair_pin = prior.digest(b"".join(p.read_bytes() for p in pair_files))
    files = [
        *candidate,
        Path(__file__),
        Path(previous.__file__),
        Path(prior.__file__),
        Path(load.__code__.co_filename),
        OUTPUT / "PROTOCOL.md",
    ]
    old_control = previous.OUTPUT / "prediction-lock.json"
    prior.archive.base.secant_full._verify_files(previous.OUTPUT, prior.read(old_control)["files"])
    cache = {
        (r["id"], r["method"]): r
        for r in read_predictions(previous.OUTPUT / "positions.jsonl.gz").values()
    }
    with gzip.open(previous.OUTPUT / "control-positions.jsonl.gz", "rt") as stream:
        cache.update({(r["id"], r["method"]): r for r in map(json.loads, stream)})
    if diagnostic_only:
        jobs = jobs[:2]
    pending = [
        (q, m)
        for q in jobs
        for m in METHODS
        if (q["id"], m) not in cache and (q["id"] != NULL or m == solver.METHOD)
    ]
    work.mkdir(parents=True, exist_ok=False)

    def hashes():
        return {str(p.relative_to(ROOT)): prior.digest(p.read_bytes()) for p in files}

    closure = hashes()
    plan_path = OUTPUT / ("diagnostic-plan.json" if diagnostic_only else "blind-plan.json")
    save_json(
        plan_path,
        dict(
            cases=jobs,
            closure=closure,
            implementation_sha256=pin,
            inherited_control_lock_sha256=prior.digest(old_control.read_bytes()),
            cpus=list(CPUS),
            niceness=10,
            cap_s=CAP,
            deadline_s=DEADLINE,
            fresh_jobs=[[q["id"], m] for q, m in pending],
        ),
    )
    start = perf_counter()

    def work_lane(i):
        for q, m in pending[i :: len(CPUS)]:
            permit = perf_counter() - start < DEADLINE - CAP
            if not permit and m == solver.METHOD:
                raise TimeoutError("candidate batch ran beyond its predeclared budget")
            if m == solver.METHOD:
                value = attempt(q, CPUS[i], algorithms, candidate, pin)
            elif m == "paired_peaks":
                value = previous.paired_attempt(q, CPUS[i], algorithms, pair_pin, permit)
            else:
                value = prior.attempt(q, m, CPUS[i], algorithms[m], permit)
            save_json(work / f"{q['id']}-{m}.json", value)

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(work_lane, range(len(CPUS))))
    if hashes() != closure:
        raise ValueError("source changed after benchmark freeze")
    mine, controls, negative = [], [], []
    for q in jobs:
        key = q["id"]
        row = prior.read(work / f"{key}-{solver.METHOD}.json")
        if key == NULL:
            negative.append(row)
            continue
        mine.append(row)
        for m, required in (
            ("paired_peaks", pair_pin),
            ("peak_paths", algorithms["peak_paths"][1]),
        ):
            inherited = (key, m) in cache
            ctrl = cache[key, m] if inherited else prior.read(work / f"{key}-{m}.json")
            if ctrl["implementation_sha256"] != required or any(ctrl[k] != row[k] for k in MATCH):
                raise ValueError(f"{m} control differs in the native inputs for {key}")
            controls.append(dict(ctrl, cohort=q["cohort"], archived_exact=inherited))
    suffix = "diagnostic-" if diagnostic_only else ""
    sealed = {
        name: pack(OUTPUT, name, content)
        for name, content in (
            (suffix + "positions.jsonl.gz", mine),
            (suffix + "control-positions.jsonl.gz", controls),
            (suffix + "misaligned-position.jsonl.gz", negative),
        )
    }
    sealed[plan_path.name] = prior.digest(plan_path.read_bytes())
    save_json(
        OUTPUT / (suffix + "prediction-lock.json"),
        dict(
            cases=[q["id"] for q in jobs],
            files=sealed,
            fresh_attempts=len(pending),
            wall_s=perf_counter() - start,
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--diagnostic-only", action="store_true")
    args = cli.parse_args()
    run(args.work, args.diagnostic_only)
