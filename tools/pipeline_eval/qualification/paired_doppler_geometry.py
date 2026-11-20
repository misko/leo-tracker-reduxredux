"""Fit only the frozen, exact simultaneous pair ledger on the original causal catalogues."""

import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import ROOT, encoded, save_json
from ..scoring import validate_result
from ..variants import paired_doppler_geometry as model
from . import paired_doppler_trial as trial
from .armijo_finish_results import pack

OUT, world = trial.OUT, trial.world
PREDICTIONS = "paired-positions.jsonl.gz"
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (512 << 20, 512 << 20))
from tools.pipeline_eval.variants import paired_doppler_geometry as solver

q = json.load(sys.stdin)
c = q['capture']
assert set(c) == {'catalog', 'catalog_timestamp_ns', 'cutoff_utc_ns', 'anchor_utc_ns', 'duration_s'}
assert c['catalog_timestamp_ns'] <= c['cutoff_utc_ns']
capture = SimpleNamespace(**(c | {'catalog': c['catalog'].encode('ascii')}))
result = solver.evaluate(capture, q['tile'], q['scope'])
json.dump(dict(result=result, geometry_cpu_s=process_time()-cpu,
               geometry_wall_s=perf_counter()-wall,
               geometry_peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def run():
    support_lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, support_lock["files"])
    cases, wave, _ = trial.inputs()
    wanted = {q["id"]: q for q in cases}
    plan = world.read(OUT / "blind-plan.json")
    if cases != plan["cases"]:
        raise ValueError("the geometry trial must use the original preflight packet")
    with gzip.open(OUT / trial.PREDICTIONS, "rt") as stream:
        previous = [
            r
            for r in map(json.loads, stream)
            if r["method"] == trial.METHODS[0] and r["result"]["metrics"].get("supports_geometry")
        ]
    paths = [
        Path(__file__),
        Path(model.__file__),
        OUT / "GEOMETRY-PROTOCOL.md",
        OUT / "prediction-lock.json",
    ]
    hashes = {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}
    save_json(OUT / "geometry-source-lock.json", hashes)
    raw = {q["id"]: q for q in previous}

    def lane(i):
        out = []
        for q in previous[i::2]:
            spec = wanted[q["id"]]
            capture = wave if q["cohort"] == "waveform" else world.clock.data(spec, None)
            original = encoded(dict(tile=spec["tile"], capture=capture))
            if world.digest(original) != q["input_sha256"]:
                raise ValueError("geometry input is not the measured native preflight input")
            cap = {
                k: capture[k]
                for k in (
                    "anchor_utc_ns",
                    "cutoff_utc_ns",
                    "catalog_timestamp_ns",
                    "duration_s",
                    "catalog",
                )
            }
            payload = encoded(dict(capture=cap, tile=q["tile"], scope=q["result"]["metrics"]))
            prior = world.prior
            argv = prior.command(trial.CPUS[i], "peak_paths", prior.sources()["peak_paths"][0])
            argv[-1] = WORKER
            world.clock.ablation._mount(
                argv,
                [
                    Path(model.__file__),
                    Path(trial.model.__file__),
                    Path(trial.control.__file__),
                    Path(trial.control.physics.__file__),
                    Path(trial.model.native.__file__),
                    Path(world.model.geodesy.__file__),
                    *world.clock.candidate_sources(),
                ],
            )
            p = subprocess.run(argv, input=payload, capture_output=True, check=True, timeout=45)
            stats = json.loads(p.stdout)
            validate_result(stats["result"])
            print(
                q["id"],
                stats["result"]["status"],
                stats["result"]["metrics"].get("profiled_radius_km"),
                round(stats["geometry_wall_s"], 2),
                flush=True,
            )
            out.append(
                q
                | stats
                | dict(
                    geometry_input_sha256=world.digest(payload),
                    support_row_sha256=world.digest(encoded(q)),
                )
            )
        return out

    with ThreadPoolExecutor(2) as pool:
        rows = [r for group in pool.map(lane, range(2)) for r in group]
    if set(r["id"] for r in rows) != set(raw) or any(
        world.digest((ROOT / name).read_bytes()) != sha for name, sha in hashes.items()
    ):
        raise ValueError("geometry support or source changed")
    files = {
        f: world.digest((OUT / f).read_bytes())
        for f in ("geometry-source-lock.json", "prediction-lock.json", "GEOMETRY-PROTOCOL.md")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, rows)
    save_json(OUT / "geometry-lock.json", dict(cases=list(raw), files=files))


if __name__ == "__main__":
    run()
