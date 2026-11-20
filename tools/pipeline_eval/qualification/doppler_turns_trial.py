"""Measure and seal observable Doppler turns on native and simulated GLRT."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import doppler_turns as model
from . import absolute_doppler_trial as world
from . import regional_levels_trial as regional
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/track-recovery/doppler-turns"
CPUS = (8, 9)
CAP_S = 45
RSS = 512 * 1024
PREDICTIONS = "positions.jsonl.gz"
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (512 << 20, 512 << 20))
from tools.pipeline_eval.variants import doppler_turns as solver
q = json.load(sys.stdin)
assert set(q) == {'tile', 'capture'}
c = q['capture']
assert c['catalog_timestamp_ns'] <= c['cutoff_utc_ns']
capture = SimpleNamespace(**(c | {'catalog': c['catalog'].encode('ascii')}))
result = solver.measure(capture, q['tile'])
json.dump(dict(result=result, worker_s=perf_counter()-wall, cpu_s=process_time()-cpu,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def attempt(q, work, cpu):
    elapsed = perf_counter()
    payload = dict(capture=world.clock.data(q, work), tile=q["tile"])
    raw = encoded(payload)
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    mount = world.clock.ablation._mount
    mount(
        argv,
        [
            Path(model.__file__),
            Path(world.model.geodesy.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    try:
        proc = subprocess.run(argv, input=raw, check=True, capture_output=True, timeout=CAP_S)
        out = json.loads(proc.stdout)
        if out["peak_rss_kib"] > RSS:
            raise ValueError("turn worker exceeded the bound")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1700:]
        result = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(err),
            boundary=model.BOUNDARY,
            metrics={"position_attempted": False},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        out = dict(result=result)
    validate_result(out["result"])
    print(
        q["id"],
        out["result"]["status"],
        out["result"]["metrics"].get("held_arcs"),
        out["result"]["metrics"].get("modeled"),
        round(perf_counter() - elapsed, 2),
        flush=True,
    )
    return dict(
        q,
        **out,
        method=model.METHOD,
        input_sha256=world.digest(raw),
        cpu=cpu,
        native_elapsed_s=perf_counter() - elapsed,
    )


def run(work):
    work.mkdir(parents=True, mode=0o700)
    paths = [
        Path(model.__file__),
        Path(__file__),
        OUT / "PROTOCOL.md",
        *world.source_paths(),
        world.OUT / "prediction-lock.json",
    ]

    def hashed():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    sources = hashed()
    save_json(OUT / "source-lock.json", sources)
    queries = [q for q in regional.inputs() if q["cohort"] in ("diagnostic", "omitted")]
    simulated, labels_sha, seed_sha = world.simulation(work)
    queries += simulated
    if len(queries) != 8:
        raise ValueError("eight frozen offers required")
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=sources,
            cpus=list(CPUS),
            cap_s=CAP_S,
            memory_mib=512,
            private_labels_sha256=labels_sha,
            seed_sha256=seed_sha,
        ),
    )

    def lane(i):
        return [attempt(q, work, CPUS[i]) for q in queries[i::2]]

    with ThreadPoolExecutor(2) as pool:
        results = [r for group in pool.map(lane, range(2)) for r in group]
    if sources != hashed():
        raise ValueError("sources changed during the turn test")
    files = {
        name: world.digest((OUT / name).read_bytes())
        for name in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, results)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in queries], files=files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)


if __name__ == "__main__":
    main()
