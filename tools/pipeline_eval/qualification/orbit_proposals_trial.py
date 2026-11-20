"""Run physical inverse orbit proposals on the exact archived worldwide requests."""

import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import orbit_proposals as model
from . import anonymous_geometry_trial as old
from .armijo_finish_results import pack

OUT = old.OUT.parent / "orbit-proposals"
world = old.world
CPUS, CAP = (16, 17), 100
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

t, c = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (768 << 20, 768 << 20))
from tools.pipeline_eval.variants import orbit_proposals as m
q = json.load(sys.stdin)
assert set(q) == {'capture','shuffle'}
d = q['capture']
assert d['catalog_timestamp_ns'] <= d['cutoff_utc_ns']
cap = SimpleNamespace(**(d | {'catalog':d['catalog'].encode('ascii')}))
result = m.solve(cap, is_null=q['shuffle'])
json.dump(dict(result=result, cpu_s=process_time()-c, worker_s=perf_counter()-t,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),sys.stdout,allow_nan=False)
"""


def authority():
    lock = old.OUT / "prediction-lock.json"
    receipt = world.read(lock)
    world.verify(old.OUT, receipt["files"])
    selected = world.read(old.OUT / "blind-plan.json")["cases"]
    if [a["id"] for a in selected] != receipt["cases"]:
        raise ValueError("the worldwide comparator roster changed")
    with gzip.open(old.OUT / "positions.jsonl.gz", "rt") as stream:
        results = {r["id"]: r for r in map(json.loads, stream) if r["method"] == old.METHODS[0]}
    if set(results) != set(receipt["cases"]):
        raise ValueError("the corpus is missing archived global predictions")
    return lock, selected, results


def run():
    lock, selected, pinned = authority()
    paths = [Path(model.__file__), Path(model.forward.__file__)]
    paths.extend(
        ROOT / "tools/pipeline_eval/variants" / (n + ".py")
        for n in (
            "joint_pass",
            "pass_hypotheses",
            "absolute_doppler",
            "doppler_turns",
        )
    )
    paths.append(ROOT / "tools/pipeline_eval/scoring.py")
    frozen = {
        str(p.relative_to(ROOT)): world.digest(p.read_bytes())
        for p in (
            *paths,
            lock,
            Path(__file__),
            OUT / "PROTOCOL.md",
            old.OUT / "source-lock.json",
        )
    }
    save_json(OUT / "source-lock.json", frozen)
    save_json(OUT / "blind-plan.json", dict(cases=selected, cpus=list(CPUS), cap_s=CAP))

    def lane(i):
        command = old.previous.command(CPUS[i], WORKER, paths)
        results = []
        for q in selected[i::2]:
            start = perf_counter()
            cap = old.load(q["recording"])
            payload = encoded(
                dict(
                    capture=vars(cap) | {"catalog": cap.catalog.decode("ascii")},
                    shuffle=q["shuffle"],
                )
            )
            digest = world.digest(payload)
            if pinned[q["id"]]["input_sha256"] != digest:
                raise ValueError("physical orbit proposal received different GLRT or causal input")
            try:
                p = subprocess.run(
                    command, input=payload, capture_output=True, check=True, timeout=CAP
                )
                entry = json.loads(p.stdout)
            except (OSError, ValueError, subprocess.SubprocessError) as err:
                message = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
                entry = dict(
                    result=dict(
                        status="timed_out"
                        if isinstance(err, subprocess.TimeoutExpired)
                        else "failed",
                        reason=message or str(err),
                        boundary=model.BOUNDARY,
                        metrics={},
                        arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
                    )
                )
            validate_result(entry["result"])
            elapsed = perf_counter() - start
            print(
                q["id"],
                entry["result"]["status"],
                entry["result"]["metrics"].get("inverse_points"),
                entry["result"]["metrics"].get("held_lead"),
                round(elapsed, 2),
                flush=True,
            )
            results.append(
                dict(
                    q,
                    method=model.METHOD,
                    native_elapsed_s=elapsed,
                    input_sha256=digest,
                    cpu=CPUS[i],
                    **entry,
                )
            )
        return results

    with ThreadPoolExecutor(2) as executor:
        rows = [row for lane_rows in executor.map(lane, range(2)) for row in lane_rows]
    if any(world.digest((ROOT / n).read_bytes()) != d for n, d in frozen.items()):
        raise ValueError("trial source closure changed while evaluating")
    files = {
        f: world.digest((OUT / f).read_bytes()) for f in ("source-lock.json", "blind-plan.json")
    }
    files["positions.jsonl.gz"] = pack(OUT, "positions.jsonl.gz", rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in selected], files=files))


if __name__ == "__main__":
    run()
