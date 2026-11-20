"""Bind native/causal inputs and run the worldwide pass-profile test before scoring."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import anonymous_geometry as model
from . import clock_geometry_trial as previous
from .armijo_finish_results import pack
from .cold_input import load

OUT = ROOT / "reports/2026_11_19_receiver_screening/antenna-confirmation/anonymous-geometry"
world = previous.world
METHODS = model.METHOD, model.CONTROL
CPUS, CAP = (18, 19), 100
REAL = "DS26-0261", "DS29-0519"
OMITTED = "DS26-0070-omitted", "DS29-0316-omitted"
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (768 << 20, 768 << 20))
from tools.pipeline_eval.variants import anonymous_geometry as solver
q = json.load(sys.stdin)
assert set(q) == {'capture','shuffle'}
d = q['capture']
assert d['catalog_timestamp_ns'] <= d['cutoff_utc_ns']
cap = SimpleNamespace(**(d | {'catalog':d['catalog'].encode('ascii')}))
r = solver.solve(cap, is_null=q['shuffle'])
json.dump(dict(results=r, cpu_s=process_time()-cpu, worker_s=perf_counter()-wall,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),sys.stdout,allow_nan=False)
"""


def queries():
    root = world.prior.archive.REPORT
    lock = root / "prediction-lock.json"
    world.verify(root, world.read(lock)["files"])
    indexed = {r["id"]: r for r in world.read(root / "plan.json")["cases"]}
    selected = []
    for group, keys in (("containing", REAL), ("omitted", OMITTED)):
        for key in keys:
            q = indexed[key]
            p = q["packet"]
            selected.append(
                dict(
                    id=key,
                    recording=q["recording"],
                    cohort=group,
                    tile=p["offer"],
                    native_sha256=p["native"]["sha256"],
                    catalog_sha256=p["catalogue"]["sha256"],
                    cutoff=p["cutoff"],
                    collected=p["catalog_timestamp"],
                    shuffle=False,
                    original_request_sha256=world.digest(encoded(p)),
                )
            )
    selected.extend(
        dict(q, id=q["id"] + "-profile-shuffle", cohort="shuffle", shuffle=True)
        for q in selected[:2]
    )
    return selected, lock


def attempt(q, cpu, overrides):
    start = perf_counter()
    capture = load(q["recording"])
    if (
        capture.native_sha256,
        capture.catalog_sha256,
        capture.cutoff_utc_ns,
        capture.catalog_timestamp_ns,
    ) != tuple(q[k] for k in ("native_sha256", "catalog_sha256", "cutoff", "collected")):
        raise ValueError("anonymous geometry received a different frozen capture")
    raw = vars(capture) | {"catalog": capture.catalog.decode("ascii")}
    payload = encoded(dict(capture=raw, shuffle=q["shuffle"]))
    command = previous.command(cpu, WORKER, overrides)
    try:
        p = subprocess.run(command, input=payload, capture_output=True, check=True, timeout=CAP)
        output = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        message = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        output = dict(
            results=[
                dict(
                    status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                    reason=message or str(err),
                    boundary=model.BOUNDARY,
                    metrics={},
                    arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
                )
            ]
            * len(METHODS)
        )
    elapsed = perf_counter() - start
    rows = []
    for method, result in zip(METHODS, output.pop("results"), strict=True):
        validate_result(result)
        print(
            q["id"],
            method,
            result["status"],
            result["metrics"].get("held_lead"),
            round(elapsed, 2),
            flush=True,
        )
        rows.append(
            dict(
                q,
                method=method,
                result=result,
                input_sha256=world.digest(payload),
                cpu=cpu,
                native_elapsed_s=elapsed,
                **output,
            )
        )
    return rows


def run():
    selected, authority = queries()
    imports = (
        model.__file__,
        ROOT / "tools/pipeline_eval/variants/joint_pass.py",
        ROOT / "tools/pipeline_eval/variants/pass_hypotheses.py",
        ROOT / "tools/pipeline_eval/variants/absolute_doppler.py",
    )
    sources = [Path(p) for p in imports] + [
        Path(__file__),
        authority,
        OUT / "PROTOCOL.md",
        ROOT / "tools/pipeline_eval/reference/grid.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        *world.source_paths(),
    ]
    frozen = {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in sources}
    save_json(OUT / "source-lock.json", frozen)
    save_json(OUT / "blind-plan.json", dict(cases=selected, cpus=list(CPUS), cap_s=CAP))

    def lane(i):
        return [r for q in selected[i::2] for r in attempt(q, CPUS[i], imports)]

    with ThreadPoolExecutor(2) as executor:
        rows = [r for group in executor.map(lane, range(2)) for r in group]
    if any(world.digest((ROOT / p).read_bytes()) != h for p, h in frozen.items()):
        raise ValueError("inference source changed during run")
    files = {
        f: world.digest((OUT / f).read_bytes()) for f in ("source-lock.json", "blind-plan.json")
    }
    files["positions.jsonl.gz"] = pack(OUT, "positions.jsonl.gz", rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in selected], files=files))


if __name__ == "__main__":
    run()
