"""Seal steepest-descent timing and regional hypotheses from anonymous native GLRT."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import doppler_inflection as model
from . import doppler_turns_trial as turns
from .armijo_finish_results import pack

OUT = turns.OUT.parent / "doppler-inflection"
world = turns.world
PREDICTIONS = "positions.jsonl.gz"
WORKER = turns.WORKER.replace(
    "import doppler_turns as solver", "import doppler_inflection as solver"
)


def attempt(q, work, cpu):
    elapsed = perf_counter()
    raw = encoded(dict(capture=world.clock.data(q, work), tile=q["tile"]))
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(
        argv,
        [
            Path(model.__file__),
            Path(turns.model.__file__),
            Path(world.model.geodesy.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    try:
        proc = subprocess.run(argv, input=raw, check=True, capture_output=True, timeout=turns.CAP_S)
        out = json.loads(proc.stdout)
        if out["peak_rss_kib"] > turns.RSS:
            raise ValueError("worker exceeded memory bound")
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
    result = out["result"]
    validate_result(result)
    metrics = result["metrics"]
    print(
        q["id"],
        result["status"],
        result["reason"],
        len(metrics.get("events", [])),
        metrics.get("centre_modeled_events"),
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
        Path(turns.model.__file__),
        Path(turns.__file__),
        Path(__file__),
        OUT / "PROTOCOL.md",
        *world.source_paths(),
        world.OUT / "prediction-lock.json",
    ]

    def hashed():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    sources = hashed()
    save_json(OUT / "source-lock.json", sources)
    queries = [q for q in turns.regional.inputs() if q["cohort"] in ("diagnostic", "omitted")]
    synthetic, labels, seed = world.simulation(work)
    queries += synthetic
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=sources,
            cpus=list(turns.CPUS),
            cap_s=turns.CAP_S,
            memory_mib=512,
            private_labels_sha256=labels,
            seed_sha256=seed,
        ),
    )

    def lane(i):
        return [attempt(q, work, turns.CPUS[i]) for q in queries[i::2]]

    with ThreadPoolExecutor(2) as pool:
        rows = [r for group in pool.map(lane, range(2)) for r in group]
    if len(rows) != 8 or sources != hashed():
        raise ValueError("trial source or roster changed during experiment")
    files = {
        name: world.digest((OUT / name).read_bytes())
        for name in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in queries], files=files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)


if __name__ == "__main__":
    main()
