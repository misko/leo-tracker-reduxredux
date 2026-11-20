"""Seal a bounded measured relative-clock fallback on six exact archive requests."""

import json
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, save_json
from ..scoring import ARMS, validate_result
from ..variants import clock_geometry_pooled as model
from . import clock_geometry_trial as trial
from .armijo_finish_results import pack

OUT, world = trial.OUT, trial.world
PREDICTIONS = "positions.jsonl.gz"
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall,cpu = perf_counter(),process_time()
setrlimit(RLIMIT_AS,(512 << 20,512 << 20))
from tools.pipeline_eval.variants import clock_geometry_pooled as solver
q = json.load(sys.stdin)
c=q['capture']
assert set(q) == {'capture','tile'} and c['catalog_timestamp_ns'] <= c['cutoff_utc_ns']
cap = SimpleNamespace(**(c | {'catalog':c['catalog'].encode('ascii')}))
clock_wall,clock_cpu = perf_counter(),process_time()
clock = solver.calibrate(cap)
cw,cc = perf_counter()-clock_wall,process_time()-clock_cpu
result = solver.evaluate(cap,q['tile'],clock)
json.dump(dict(result=result,clock=clock,calibration_cpu_s=cc,calibration_wall_s=cw,
               cpu_s=process_time()-cpu,worker_s=perf_counter()-wall,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),sys.stdout,allow_nan=False)
"""


def run():
    receipt = world.read(OUT / "measurement-lock.json")
    world.verify(OUT, receipt["files"])
    q, wave, pinned = trial.keys()
    if q != world.read(OUT / "blind-plan.json")["cases"] or any(
        row["result"]["timing"]["geometry_eligible"]
        for row in world.read(OUT / "clock-measurements.json")["records"]
    ):
        raise ValueError(
            "fallback requires the original position roster and unsupported epoch closure"
        )
    sources = [
        Path(__file__),
        Path(model.__file__),
        Path(model.base.__file__),
        Path(model.base.physics.__file__),
        Path(trial.__file__),
        OUT / "POOLED-PROTOCOL.md",
        OUT / "measurement-lock.json",
        trial.previous.OUT / "prediction-lock.json",
    ]
    frozen = {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in sources}
    save_json(OUT / "source-lock.json", frozen)
    out = []
    for spec in q:
        start = perf_counter()
        _, payload = trial.envelope(spec, wave)
        digest = world.digest(payload)
        if digest != pinned[spec["id"], trial.previous.METHODS[0]]["input_sha256"]:
            raise ValueError("paired shared clock control and fallback got different requests")
        try:
            paths = (
                model.__file__,
                model.measured.__file__,
                model.base.__file__,
                model.base.physics.__file__,
            )
            p = subprocess.run(
                trial.command(2, WORKER, paths),
                input=payload,
                capture_output=True,
                check=True,
                timeout=45,
            )
            row = json.loads(p.stdout)
        except (OSError, ValueError, subprocess.SubprocessError) as err:
            detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-2000:]
            row = dict(
                result=dict(
                    status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                    reason=detail or str(err),
                    boundary=model.BOUNDARY,
                    metrics={"position_attempted": False},
                    arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
                )
            )
        validate_result(row["result"])
        print(
            spec["id"],
            row["result"]["status"],
            row["result"]["metrics"].get("applied_relative_bands"),
            round(perf_counter() - start, 2),
            flush=True,
        )
        out.append(
            dict(
                spec,
                **row,
                method=model.METHOD,
                cpu=2,
                input_sha256=digest,
                native_elapsed_s=perf_counter() - start,
            )
        )
    if any(world.digest((ROOT / n).read_bytes()) != h for n, h in frozen.items()):
        raise ValueError("fallback science source changed")
    files = {
        n: world.digest((OUT / n).read_bytes())
        for n in ("source-lock.json", "blind-plan.json", "measurement-lock.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, out)
    save_json(OUT / "prediction-lock.json", dict(cases=[r["id"] for r in out], files=files))


if __name__ == "__main__":
    run()
