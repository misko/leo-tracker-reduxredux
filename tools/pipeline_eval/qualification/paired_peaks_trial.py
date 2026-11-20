"""Replay synchronized dual-receiver peak fusion and exact graphless controls."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import paired_peaks as paired
from . import peak_paths_trial as prior
from .armijo_finish_results import pack
from .cold_input import load

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/integration/paired-peaks"
CPUS = (8, 9)
DEADLINE = 480
CAP = 75
DIAGNOSTIC = ("DS26-0197", "DS29-0316")
CONFIRMATION = ("DS26-0317", "DS26-0070", "DS29-0174", "DS29-0247")
OMITTED = ("DS26-0277-omitted", "DS29-0604-omitted")
NULL = "DS26-0197-misaligned"
IDS = (*DIAGNOSTIC, *CONFIRMATION, *OMITTED, NULL)
WORKER = """
import json
import sys
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from types import SimpleNamespace

began = perf_counter(), process_time()
request = json.load(sys.stdin)
from tools.pipeline_eval.variants import paired_peaks as solver
from tools.pipeline_eval.variants import peak_paths
from tools.pipeline_eval.reference import grid

law = Path(solver.__file__)
stock = Path(peak_paths.__file__)
files = law, stock, stock.with_suffix('.c'), Path(grid.__file__)
source_digest = sha256(b''.join(path.read_bytes() for path in files)).hexdigest()
if source_digest != request['implementation_sha256']:
    raise ValueError('paired worker source cannot be authenticated')
data = request['capture']
capture = SimpleNamespace(**dict(data, catalog=data['catalog'].encode('ascii')))
result, trace = solver.solve(capture, tile=request['tile'], misalign=request['misalign'])
json.dump(dict(result=result, trace=trace, worker_s=perf_counter()-began[0],
               cpu_s=process_time()-began[1], peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),
          sys.stdout, allow_nan=False)
"""


def rows():
    parent = prior.archive.REPORT
    seal = prior.read(parent / "prediction-lock.json")
    prior.archive.base.secant_full._verify_files(parent, seal["files"])
    stock = {r["id"]: r for r in prior.read(parent / "plan.json")["cases"]}
    result = []
    for scope, ids in (
        ("diagnostic", DIAGNOSTIC),
        ("confirmation", CONFIRMATION),
        ("omitted", OMITTED),
    ):
        for key in ids:
            original = stock[key]
            packet = original["packet"]
            result.append(
                dict(
                    id=key,
                    recording=original["recording"],
                    cohort=scope,
                    original_request_sha256=prior.digest(encoded(packet)),
                    tile=packet["offer"],
                    cutoff=packet["cutoff"],
                    collected=packet["catalog_timestamp"],
                    native_sha256=packet["native"]["sha256"],
                    catalog_sha256=packet["catalogue"]["sha256"],
                    shuffle=False,
                    misalign=False,
                )
            )
    return [*result, dict(result[0], id=NULL, cohort="misaligned", misalign=True)]


def paired_attempt(q, cpu, methods, source, permit):
    began = perf_counter()
    capture = load(q["recording"])
    if (
        capture.native_sha256,
        capture.catalog_sha256,
        capture.cutoff_utc_ns,
        capture.catalog_timestamp_ns,
    ) != (q["native_sha256"], q["catalog_sha256"], q["cutoff"], q["collected"]):
        raise ValueError("paired native source is different from the original query")
    argv = prior.command(cpu, "peak_paths", methods["peak_paths"][0])
    argv[-1] = WORKER
    module = Path(paired.__file__)
    argv[-4:-4] = ["--ro-bind", str(module), str(Path("/worker") / module.relative_to(ROOT))]
    payload = dict(
        capture=vars(capture) | {"catalog": capture.catalog.decode("ascii")},
        tile=q["tile"],
        shuffle=False,
    )
    raw = encoded(dict(payload, misalign=q["misalign"], implementation_sha256=source))
    try:
        if not permit:
            raise TimeoutError("paired batch deadline exhausted")
        p = subprocess.run(argv, input=raw, capture_output=True, check=True, timeout=CAP)
        out = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1500:]
        out = dict(
            result=dict(
                status="timed_out"
                if isinstance(err, (TimeoutError, subprocess.TimeoutExpired))
                else "failed",
                boundary=paired.BOUNDARY,
                reason=detail or str(err),
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            )
        )
    validate_result(out["result"])
    result = dict(
        q,
        method=paired.METHOD,
        cpu=cpu,
        input_sha256=prior.digest(encoded(payload)),
        implementation_sha256=source,
        native_elapsed_s=perf_counter() - began,
        **out,
    )
    print(
        q["id"],
        paired.METHOD,
        out["result"]["status"],
        out["result"]["reason"],
        out["result"]["metrics"].get("selected_paths"),
        round(result["native_elapsed_s"], 2),
        flush=True,
    )
    return result


def run(work):
    jobs = rows()
    algorithms = prior.sources()
    files = [
        Path(paired.__file__),
        *algorithms["peak_paths"][0],
        ROOT / "tools/pipeline_eval/reference/grid.py",
    ]
    source = prior.digest(b"".join(p.read_bytes() for p in files))
    all_files = [
        *files,
        *algorithms["folded_doppler"][0],
        Path(__file__),
        Path(prior.__file__),
        Path(load.__code__.co_filename),
        OUTPUT / "PROTOCOL.md",
    ]
    closure = {str(p.relative_to(ROOT)): prior.digest(p.read_bytes()) for p in all_files}
    old = prior.read(prior.OUTPUT / "prediction-lock.json")
    prior.archive.base.secant_full._verify_files(prior.OUTPUT, old["files"])
    cache = {
        m: read_predictions(prior.OUTPUT / f)
        for m, f in (
            ("peak_paths", "positions.jsonl.gz"),
            ("folded_doppler", "folded-positions.jsonl.gz"),
        )
    }
    planned = []
    for q in jobs:
        planned.append((q, paired.METHOD))
        if q["misalign"]:
            continue
        for method in cache:
            if q["id"] not in cache[method]:
                planned.append((q, method))
    work.mkdir(parents=True, exist_ok=False)
    save_json(
        OUTPUT / "blind-plan.json",
        dict(
            cases=jobs,
            closure=closure,
            frozen_pair_sha256=source,
            old_control_lock_sha256=prior.digest(
                (prior.OUTPUT / "prediction-lock.json").read_bytes()
            ),
            elapsed_budget_s=DEADLINE,
            per_worker_cap_s=CAP,
            cpus=list(CPUS),
            niceness=10,
            fresh_jobs=[[q["id"], m] for q, m in planned],
        ),
    )
    start = perf_counter()

    def lane(i):
        for q, method in planned[i::2]:
            permit = perf_counter() - start < DEADLINE - CAP - 10
            if method == paired.METHOD:
                row = paired_attempt(q, CPUS[i], algorithms, source, permit)
            else:
                row = prior.attempt(q, method, CPUS[i], algorithms[method], permit)
            save_json(work / f"{q['id']}-{method}.json", row)

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, range(2)))
    if {str(p.relative_to(ROOT)): prior.digest(p.read_bytes()) for p in all_files} != closure:
        raise ValueError("paired source changed after evidence lock")
    candidate, trace, negative, control = [], [], [], []
    for q in jobs:
        key = q["id"]
        row = prior.read(work / f"{key}-{paired.METHOD}.json")
        if "trace" in row:
            trace.append(dict(id=key, paths=row.pop("trace")))
        if q["misalign"]:
            negative.append(row)
            continue
        candidate.append(row)
        for method, archive in cache.items():
            inherited = key in archive
            previous = archive[key] if inherited else prior.read(work / f"{key}-{method}.json")
            if previous.get("implementation_sha256") != algorithms[method][1] or any(
                row[k] != previous[k]
                for k in (
                    "input_sha256",
                    "original_request_sha256",
                    "tile",
                    "native_sha256",
                    "catalog_sha256",
                )
            ):
                raise ValueError(f"{key} control does not use the identical native handoff")
            control.append(dict(previous, cohort=q["cohort"], archived_exact=bool(inherited)))
    packed = {
        name: pack(OUTPUT, name, values)
        for name, values in (
            ("positions.jsonl.gz", candidate),
            ("control-positions.jsonl.gz", control),
            ("misaligned-position.jsonl.gz", negative),
            ("selected-paths.jsonl.gz", trace),
        )
    }
    packed["blind-plan.json"] = prior.digest((OUTPUT / "blind-plan.json").read_bytes())
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(
            files=packed,
            wall_s=perf_counter() - start,
            cases=list(IDS),
            fresh_attempts=len(planned),
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    run(cli.parse_args().work)
