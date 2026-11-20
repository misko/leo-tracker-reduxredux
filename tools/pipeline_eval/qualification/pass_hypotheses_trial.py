"""Replay two-line geographic hypotheses on frozen archive and waveform offers."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import pass_hypotheses as model
from . import trackless_likelihood_trial as previous
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/arrival-and-timing/pass-hypotheses"
world, shell = previous.world, previous.shell
CPUS = 10, 11
PREDICTIONS = "positions.jsonl.gz"
WORKER = previous.WORKER.replace(
    "import trackless_likelihood as solver", "import pass_hypotheses as solver"
)
ROOF = ("DS26-0168", "DS29-0519")


def attempt(q, data, cpu):
    start = perf_counter()
    capture = data if q["cohort"] == "waveform" else world.clock.data(q, None)
    payload = encoded(dict(capture=capture, tile=q["tile"]))
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(
        argv,
        [
            Path(model.__file__),
            Path(model.native.__file__),
            Path(world.model.geodesy.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    try:
        p = subprocess.run(
            argv, input=payload, capture_output=True, check=True, timeout=shell.CAP_S
        )
        receipt = json.loads(p.stdout)
        if receipt["peak_rss_kib"] > shell.RSS:
            raise ValueError("worker exceeded memory limit")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        log = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-2000:]
        result = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=log or str(err),
            boundary=model.BOUNDARY,
            metrics={"position_attempted": False},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        receipt = dict(result=[result] * 2)
    elapsed = perf_counter() - start
    rows = []
    for method, result in zip(model.METHODS, receipt.pop("result"), strict=True):
        validate_result(result)
        print(
            q["id"],
            method,
            result["status"],
            result["reason"],
            result["metrics"].get("in_tile_intersections"),
            round(elapsed, 2),
            flush=True,
        )
        rows.append(
            dict(
                q,
                **receipt,
                result=result,
                method=method,
                cpu=cpu,
                input_sha256=world.digest(payload),
                native_elapsed_s=elapsed,
            )
        )
    return rows


def run(work):
    work.mkdir(parents=True, mode=0o700)
    cap, wave = previous.waveform()
    archive = world.OUT / "prediction-lock.json"
    world.verify(world.OUT, world.read(archive)["files"])
    offers = [
        q for q in shell.regional.inputs() if q["id"] in ROOF or q["cohort"] == "omitted"
    ] + cap
    if len(offers) != 6:
        raise ValueError("expected four real requests and both original waveform offers")
    paths = [
        Path(model.__file__),
        Path(model.native.__file__),
        Path(__file__),
        Path(previous.__file__),
        Path(shell.__file__),
        OUT / "PROTOCOL.md",
        archive,
        previous.WAVE / "detector-lock.json",
        *world.source_paths(),
    ]

    def pinned():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    sources = pinned()
    save_json(OUT / "source-lock.json", sources)
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=offers,
            sources=sources,
            cpus=list(CPUS),
            max_s=shell.CAP_S,
            memory_mib=512,
        ),
    )

    def lane(i):
        return [r for q in offers[i::2] for r in attempt(q, wave, CPUS[i])]

    with ThreadPoolExecutor(2) as pool:
        results = [r for group in pool.map(lane, range(2)) for r in group]
    if sources != pinned():
        raise ValueError("prospectively frozen source changed during numerical work")
    files = {
        name: world.digest((OUT / name).read_bytes())
        for name in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, results)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in offers], files=files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)


if __name__ == "__main__":
    main()
