"""Measure exact native timing/clock evidence independently of site and orbit labels."""

import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..__main__ import ROOT, encoded, save_json
from ..variants import clock_geometry as model
from . import paired_doppler_trial as previous

OUT = ROOT / "reports/2026_11_19_receiver_screening/pilot-influence/clock-geometry"
CPUS = 2, 3
world = previous.world
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall,cpu = perf_counter(),process_time()
setrlimit(RLIMIT_AS,(512 << 20,512 << 20))
from tools.pipeline_eval.variants import clock_geometry as clock
q = json.load(sys.stdin)
cap = SimpleNamespace(**q['capture'])
out = dict(timing=clock.timing(cap, q['pairs']), relative_clock=clock.rates(cap))
json.dump(dict(result=out, cpu_s=process_time()-cpu, worker_s=perf_counter()-wall,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),sys.stdout,allow_nan=False)
"""


def keys():
    lock = world.read(previous.OUT / "prediction-lock.json")
    world.verify(previous.OUT, lock["files"])
    offers, wave, _ = previous.inputs()
    if offers != world.read(previous.OUT / "blind-plan.json")["cases"]:
        raise ValueError("the pinned paired-Doppler request roster changed")
    with gzip.open(previous.OUT / previous.PREDICTIONS, "rt") as stream:
        inputs = {(r["id"], r["method"]): r for r in map(json.loads, stream)}
    return offers, wave, inputs


def envelope(q, wave):
    data = wave if q["cohort"] == "waveform" else world.clock.data(q, None)
    return data, encoded(dict(capture=data, tile=q["tile"]))


def command(cpu, worker, paths):
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = worker
    world.clock.ablation._mount(
        argv,
        [Path(p) for p in paths]
        + [
            Path(previous.model.__file__),
            Path(previous.model.native.__file__),
            Path(world.model.geodesy.__file__),
            Path(model.hardware.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    return argv


def run():
    offers, wave, pinned = keys()
    paths = [
        Path(__file__),
        Path(model.__file__),
        Path(model.hardware.__file__),
        Path(previous.model.__file__),
        Path(previous.model.native.__file__),
        OUT / "PROTOCOL.md",
        previous.OUT / "prediction-lock.json",
        *world.source_paths(),
    ]
    source = {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}
    save_json(OUT / "measurement-source-lock.json", source)
    by_capture = {}
    for q in offers:
        by_capture.setdefault(q["recording"], q)
    selected = list(by_capture.values())
    save_json(OUT / "blind-plan.json", dict(cases=offers, cpus=list(CPUS), cap_s=45))

    def lane(i):
        records = []
        for q in selected[i::2]:
            verified = pinned[q["id"], previous.METHODS[0]]
            original, packet = envelope(q, wave)
            if world.digest(packet) != verified["input_sha256"]:
                raise ValueError("original native packet differs from prior verified pair support")
            raw = dict(
                capture={k: v for k, v in original.items() if k != "catalog"},
                pairs=verified["result"]["metrics"]["pairs"],
            )
            payload = encoded(raw)
            p = subprocess.run(
                command(CPUS[i], WORKER, [model.__file__]),
                input=payload,
                capture_output=True,
                check=True,
                timeout=45,
            )
            stats = json.loads(p.stdout)
            records.append(
                dict(
                    recording=q["recording"],
                    measured_id=q["id"],
                    native_sha256=q["native_sha256"],
                    worker_input_sha256=world.digest(payload),
                    measured_pair_sha256=world.digest(encoded(raw["pairs"])),
                    **stats,
                )
            )
            print(
                q["id"],
                len(stats["result"]["timing"]["pieces"]),
                stats["result"]["timing"]["geometry_eligible"],
                flush=True,
            )
        return records

    with ThreadPoolExecutor(2) as executor:
        records = [q for group in executor.map(lane, range(2)) for q in group]
    if len(records) != 3 or any(
        world.digest((ROOT / p).read_bytes()) != s for p, s in source.items()
    ):
        raise ValueError("measurement roster or source changed")
    save_json(OUT / "clock-measurements.json", dict(records=records))
    artifacts = ("clock-measurements.json", "measurement-source-lock.json", "blind-plan.json")
    save_json(
        OUT / "measurement-lock.json",
        dict(
            files={name: world.digest((OUT / name).read_bytes()) for name in artifacts},
            cases=[q["id"] for q in offers],
        ),
    )


if __name__ == "__main__":
    run()
