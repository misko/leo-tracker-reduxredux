"""Run peak-path and graphless controls from the same sealed native handoff."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import peak_paths
from . import native_joint_full as archive
from .armijo_finish_results import pack
from .cold_input import load
from .cold_missing import _sandbox, _sources
from .prefix_figures import TIMING_IDS

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/deployment/peak-paths"
CPUS = (8, 9, 10, 11)
CAP = 75
DIAGNOSTIC = ("DS26-0197", "DS29-0316")
SHUFFLE = "DS26-0197-shuffle"
WORKER = """
import json
import sys
from hashlib import sha256
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from types import SimpleNamespace

initial = perf_counter(), process_time()
request = json.load(sys.stdin)
if request['method']=='peak_paths':
    from tools.pipeline_eval.variants import peak_paths as solver
else:
    import solver
source = Path(solver.__file__)
digest = sha256(source.read_bytes()+source.with_suffix('.c').read_bytes()).hexdigest()
if digest != request['implementation_sha256']:
    raise ValueError('worker source differs from predeclared binding')
data = request['capture']
capture = SimpleNamespace(**dict(data, catalog=data['catalog'].encode('ascii')))
if request['method']=='peak_paths':
    result, trace = solver.solve(capture, tile=request['tile'], shuffle=request['shuffle'])
else:
    result = solver.solve(capture, tile=request['tile']['center'])
    trace = []
json.dump(dict(result=result, trace=trace, worker_s=perf_counter()-initial[0],
               cpu_s=process_time()-initial[1], peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),
          sys.stdout, allow_nan=False)
"""


def digest(data):
    return sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def bindings():
    root = archive.REPORT
    seal = read(root / "prediction-lock.json")
    archive.base.secant_full._verify_files(root, seal["files"])
    source = read(root / "plan.json")["cases"]
    by_id = {r["id"]: r for r in source}
    selected = dict(diagnostic=list(DIAGNOSTIC), confirmation=[], omitted=[])
    excluded = set(DIAGNOSTIC) | set(TIMING_IDS)
    for mode, count, key in (("roof", 3, "confirmation"), ("omitted", 1, "omitted")):
        for group in ("DS26-", "DS29-"):
            pool = [
                row
                for row in source
                if row["recording"].startswith(group)
                and row["recording"] not in excluded
                and row["cohort"] == mode
                and (mode != "omitted" or row["id"].endswith("-omitted"))
            ]
            choices = sorted(
                pool, key=lambda r: digest(("peak-paths-20261119/" + r["id"]).encode())
            )[:count]
            if len(choices) != count:
                raise ValueError("blind peak path cohort is incomplete")
            selected[key].extend(r["id"] for r in choices)
            excluded.update(r["recording"] for r in choices)
    frames = []
    for mode, ids in selected.items():
        for case in ids:
            ref = by_id[case]
            packet = ref["packet"]
            frames.append(
                dict(
                    id=case,
                    recording=ref["recording"],
                    cohort=mode,
                    native_sha256=packet["native"]["sha256"],
                    catalog_sha256=packet["catalogue"]["sha256"],
                    cutoff=packet["cutoff"],
                    collected=packet["catalog_timestamp"],
                    tile=packet["offer"],
                    original_request_sha256=digest(encoded(packet)),
                    shuffle=False,
                )
            )
    frames.append(dict(frames[0], id=SHUFFLE, cohort="shuffle", shuffle=True))
    return frames, digest((root / "plan.json").read_bytes())


def sources():
    path = Path(peak_paths.__file__)
    ours = [path, path.with_suffix(".c")]
    folded, pin = _sources("folded_doppler")
    return dict(
        peak_paths=(ours, digest(b"".join(p.read_bytes() for p in ours))),
        folded_doppler=(folded, pin),
    )


def command(cpu, method, paths):
    argv = _sandbox(cpu, paths)
    argv[-1] = WORKER
    if method == "peak_paths":
        for path in paths:
            argv[argv.index(f"/worker/solver{path.suffix}")] = str(
                Path("/worker") / path.relative_to(ROOT)
            )
        named = ROOT / "tools/pipeline_eval/reference/grid.py"
        argv[-4:-4] = ["--ro-bind", str(named), str(Path("/worker") / named.relative_to(ROOT))]
    return ["nice", "-n", "10", *argv]


def attempt(q, method, cpu, source, permit):
    start = perf_counter()
    data = load(q["recording"])
    if (data.native_sha256, data.catalog_sha256, data.cutoff_utc_ns, data.catalog_timestamp_ns) != (
        q["native_sha256"],
        q["catalog_sha256"],
        q["cutoff"],
        q["collected"],
    ):
        raise ValueError("native archive clock or digest differs from sealed request")
    request = dict(
        capture=vars(data) | {"catalog": data.catalog.decode("ascii")},
        tile=q["tile"],
        shuffle=q["shuffle"],
        method=method,
        implementation_sha256=source[1],
    )
    raw = encoded(request)
    observed = digest(encoded({k: request[k] for k in ("capture", "tile", "shuffle")}))
    try:
        if not permit:
            raise TimeoutError("batch deadline left no process budget")
        child = subprocess.run(
            command(cpu, method, source[0]), input=raw, capture_output=True, check=True, timeout=CAP
        )
        output = json.loads(child.stdout)
    except (ValueError, OSError, subprocess.SubprocessError) as err:
        text = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1300:]
        output = dict(
            result=dict(
                status="timed_out"
                if isinstance(err, (subprocess.TimeoutExpired, TimeoutError))
                else "failed",
                reason=text or str(err),
                boundary=peak_paths.BOUNDARY,
                metrics={},
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
            )
        )
    validate_result(output["result"])
    row = dict(
        q,
        method=method,
        cpu=cpu,
        input_sha256=observed,
        implementation_sha256=source[1],
        native_elapsed_s=perf_counter() - start,
        **output,
    )
    print(
        q["id"],
        method,
        row["result"]["status"],
        row["result"]["metrics"].get("selected_paths"),
        round(row["native_elapsed_s"], 2),
        flush=True,
    )
    return row


def run(work):
    frame, stock = bindings()
    implementations = sources()
    code = [
        Path(__file__),
        Path(load.__code__.co_filename),
        ROOT / "tools/pipeline_eval/reference/grid.py",
        OUTPUT / "PROTOCOL.md",
    ]
    code.extend(p for paths, _ in implementations.values() for p in paths)
    frozen = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in code}
    plan = dict(
        frames=frame,
        sources=frozen,
        stock_plan_sha256=stock,
        cpus=list(CPUS),
        deadline_s=CAP,
        batch_wall_cap_s=600,
        niceness=10,
    )
    work.mkdir(parents=True, exist_ok=False)
    save_json(OUTPUT / "blind-plan.json", plan)
    started = perf_counter()
    jobs = [
        (q, method)
        for q in frame
        for method in implementations
        if not q["shuffle"] or method == "peak_paths"
    ]

    def lane(i):
        for q, method in jobs[i :: len(CPUS)]:
            row = attempt(
                q,
                method,
                CPUS[i],
                implementations[method],
                perf_counter() - started < 600 - CAP - 10,
            )
            save_json(work / f"{q['id']}-{method}.json", row)

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, range(len(CPUS))))
    if {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in code} != frozen:
        raise ValueError("scientific source changed during blind measurement")
    packed = {method: [] for method in implementations}
    trace = []
    for q, method in jobs:
        row = read(work / f"{q['id']}-{method}.json")
        if method == "peak_paths" and "trace" in row:
            trace.append(dict(id=q["id"], selected_paths=row["trace"]))
        row.pop("trace", None)
        packed[method].append(row)
    force_only = [r for r in packed["peak_paths"] if r["shuffle"]]
    files = {
        "positions.jsonl.gz": pack(
            OUTPUT, "positions.jsonl.gz", [r for r in packed["peak_paths"] if not r["shuffle"]]
        ),
        "shuffle-position.jsonl.gz": pack(OUTPUT, "shuffle-position.jsonl.gz", force_only),
        "folded-positions.jsonl.gz": pack(
            OUTPUT, "folded-positions.jsonl.gz", packed["folded_doppler"]
        ),
        "path-traces.jsonl.gz": pack(OUTPUT, "path-traces.jsonl.gz", trace),
        "blind-plan.json": digest((OUTPUT / "blind-plan.json").read_bytes()),
    }
    save_json(
        OUTPUT / "prediction-lock.json",
        dict(
            files=files,
            wall_s=perf_counter() - started,
            attempts=len(jobs),
            cases=[q["id"] for q in frame],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    run(parser.parse_args().work)
