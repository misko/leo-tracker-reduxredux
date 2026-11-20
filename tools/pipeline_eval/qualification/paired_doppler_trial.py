"""Seal exact pair support and the shared-clock individual-arc control."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import numpy as np

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import joint_pass as control
from ..variants import paired_doppler as model
from . import joint_pass_trial as base
from .armijo_finish_results import pack
from .fresh_scenes import _destination

OUT = ROOT / "reports/2026_11_19_receiver_screening/receiver-choice/paired-doppler"
world, shell = base.world, base.shell
CPUS = (6, 7)
PREDICTIONS = "positions.jsonl.gz"
METHODS = (model.METHOD, "paired_doppler_shared_clock_control")
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (512 << 20, 512 << 20))
from tools.pipeline_eval.variants import paired_doppler, joint_pass

q = json.load(sys.stdin)
c = q['capture']
assert set(q) == {'tile', 'capture'} and c['catalog_timestamp_ns'] <= c['cutoff_utc_ns']
cap = SimpleNamespace(**(c | {'catalog': c['catalog'].encode('ascii')}))
p_cpu, p_wall = process_time(), perf_counter()
candidate = paired_doppler.measure(cap)
pair_cpu_s, pair_wall_s = process_time()-p_cpu, perf_counter()-p_wall
control = joint_pass.evaluate(cap, q['tile'])[0]
json.dump(dict(result=[candidate,control], worker_s=perf_counter()-wall, cpu_s=process_time()-cpu,
               pair_cpu_s=pair_cpu_s, pair_wall_s=pair_wall_s,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def displacement(q):
    key = "paired-doppler-20261119/" + q["id"]
    radians = 2 * np.pi * (int(world.digest(key.encode())[:12], 16) / 2**48)
    tile = dict(center=_destination(q["tile"]["center"], 55.0, radians), width_km=25)
    return dict(
        q,
        id=q["id"] + "-paired-omitted",
        cohort="generated-omitted",
        tile=tile,
        containing_request_sha256=q["original_request_sha256"],
        original_request_sha256=world.digest(
            encoded(dict(id=q["id"], scheme=key, original=q["original_request_sha256"], tile=tile))
        ),
    )


def inputs():
    previous = base.TRACKLESS
    seal = previous.OUT / "prediction-lock.json"
    world.verify(previous.OUT, world.read(seal)["files"])
    roof = [
        q for q in world.read(previous.OUT / "blind-plan.json")["cases"] if q["id"] in previous.ROOF
    ]
    wave, capture = previous.waveform()
    if len(roof) != 2 or len(wave) != 2:
        raise ValueError("both exact roof and waveform inputs are required")
    return roof + [displacement(q) for q in roof] + wave, capture, seal


def attempt(q, waveform, cpu):
    start = perf_counter()
    data = waveform if q["cohort"] == "waveform" else world.clock.data(q, None)
    payload = encoded(dict(tile=q["tile"], capture=data))
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(
        argv,
        [
            Path(model.__file__),
            Path(control.__file__),
            Path(control.physics.__file__),
            Path(model.native.__file__),
            Path(world.model.geodesy.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    try:
        p = subprocess.run(
            argv, input=payload, capture_output=True, check=True, timeout=shell.CAP_S
        )
        stats = json.loads(p.stdout)
        if stats["peak_rss_kib"] > shell.RSS:
            raise ValueError("worker exceeded 512 MiB limit")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        result = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(err),
            boundary=model.BOUNDARY,
            metrics={"position_attempted": False},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        stats = dict(result=[result] * len(METHODS))
    elapsed = perf_counter() - start
    outcomes = []
    for method, result in zip(METHODS, stats.pop("result"), strict=True):
        validate_result(result)
        print(
            q["id"],
            method,
            result["status"],
            result["metrics"].get("persistent_pairs"),
            round(elapsed, 2),
            flush=True,
        )
        outcomes.append(
            dict(
                q,
                method=method,
                result=result,
                **stats,
                cpu=cpu,
                native_elapsed_s=elapsed,
                input_sha256=world.digest(payload),
            )
        )
    return outcomes


def run(work):
    work.mkdir(parents=True, mode=0o700)
    cases, waveform, authority = inputs()
    paths = [
        Path(__file__),
        Path(model.__file__),
        Path(control.__file__),
        Path(model.native.__file__),
        Path(control.physics.__file__),
        Path(base.TRACKLESS.__file__),
        OUT / "PROTOCOL.md",
        authority,
        base.TRACKLESS.WAVE / "detector-lock.json",
        *world.source_paths(),
    ]

    def hashes():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    frozen = hashes()
    save_json(OUT / "source-lock.json", frozen)
    save_json(
        OUT / "blind-plan.json",
        dict(cases=cases, sources=frozen, cpus=list(CPUS), cap_s=shell.CAP_S),
    )

    def lane(i):
        return [r for q in cases[i::2] for r in attempt(q, waveform, CPUS[i])]

    with ThreadPoolExecutor(2) as pool:
        rows = [r for group in pool.map(lane, range(2)) for r in group]
    if hashes() != frozen:
        raise ValueError("source changed during paired Doppler trial")
    files = {
        p: world.digest((OUT / p).read_bytes()) for p in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in cases], files=files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)


if __name__ == "__main__":
    main()
