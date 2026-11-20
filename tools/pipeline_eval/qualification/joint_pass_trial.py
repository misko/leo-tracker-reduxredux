"""Replay joint and independent receiver drift from original anonymous native passes."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import joint_pass as model
from . import pass_hypotheses_trial as previous
from . import regional_levels_trial as regional
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/latency-and-support/joint-pass"
SIM = Path("/srv/bulk/leo-dev/20261119-regional-levels")
world, shell, CPUS = previous.world, previous.shell, previous.CPUS
PREDICTIONS = "positions.jsonl.gz"
WORKER = previous.WORKER.replace("import pass_hypotheses as solver", "import joint_pass as solver")
TRACKLESS = previous.previous


def inputs():
    authority = TRACKLESS.OUT / "prediction-lock.json"
    world.verify(TRACKLESS.OUT, world.read(authority)["files"])
    orig = world.read(TRACKLESS.OUT / "blind-plan.json")["cases"]
    wave, data = TRACKLESS.waveform()
    if wave != [q for q in orig if q["cohort"] == "waveform"]:
        raise ValueError("waveform inputs differ from the earlier independent-site seal")
    sim_lock = regional.OUT / "prediction-lock.json"
    world.verify(regional.OUT, world.read(sim_lock)["files"])
    candidates = [
        q
        for q in world.read(regional.OUT / "blind-plan.json")["cases"]
        if q["cohort"].startswith("simulated-")
    ]
    simulated = [q for q in candidates if q["recording"] == candidates[0]["recording"]]
    if len(orig) != 6 or len(simulated) != 2:
        raise ValueError("exactly six original and two factor-simulation offers are required")
    return orig + simulated, data, (authority, sim_lock)


def attempt(q, waveform, cpu):
    start = perf_counter()
    capture = waveform if q["cohort"] == "waveform" else world.clock.data(q, SIM)
    payload = encoded(dict(capture=capture, tile=q["tile"]))
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(
        argv,
        [
            Path(model.__file__),
            Path(model.tracks.__file__),
            Path(model.physics.__file__),
            Path(world.model.geodesy.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    try:
        p = subprocess.run(
            argv, input=payload, capture_output=True, check=True, timeout=shell.CAP_S
        )
        result = json.loads(p.stdout)
        if result["peak_rss_kib"] > shell.RSS:
            raise ValueError("worker exceeded address space")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        failure = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(err),
            boundary=model.BOUNDARY,
            metrics={"position_attempted": False},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        result = dict(result=[failure] * len(model.METHODS))
    elapsed = perf_counter() - start
    rows = []
    for method, r in zip(model.METHODS, result.pop("result"), strict=True):
        validate_result(r)
        print(
            q["id"],
            method,
            r["status"],
            r["reason"],
            r["metrics"].get("held_families"),
            round(elapsed, 2),
            flush=True,
        )
        rows.append(
            dict(
                q,
                method=method,
                result=r,
                **result,
                cpu=cpu,
                input_sha256=world.digest(payload),
                native_elapsed_s=elapsed,
            )
        )
    return rows


def run(work):
    work.mkdir(parents=True, mode=0o700)
    offers, wave, authorities = inputs()
    paths = [
        Path(__file__),
        Path(model.__file__),
        Path(model.tracks.__file__),
        Path(model.physics.__file__),
        Path(previous.__file__),
        Path(TRACKLESS.__file__),
        OUT / "PROTOCOL.md",
        *authorities,
        TRACKLESS.WAVE / "detector-lock.json",
        *world.source_paths(),
    ]

    def hashes():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    source = hashes()
    save_json(OUT / "source-lock.json", source)
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=offers,
            sources=source,
            cpus=list(CPUS),
            cap_s=shell.CAP_S,
            memory_mib=512,
        ),
    )

    def lane(i):
        return [r for q in offers[i::2] for r in attempt(q, wave, CPUS[i])]

    with ThreadPoolExecutor(2) as pool:
        all_rows = [r for group in pool.map(lane, range(2)) for r in group]
    if source != hashes():
        raise ValueError("sealed scientific sources changed before prediction")
    seals = {
        p: world.digest((OUT / p).read_bytes()) for p in ("source-lock.json", "blind-plan.json")
    }
    seals[PREDICTIONS] = pack(OUT, PREDICTIONS, all_rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in offers], files=seals))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)


if __name__ == "__main__":
    main()
