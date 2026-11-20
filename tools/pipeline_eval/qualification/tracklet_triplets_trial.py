"""Authenticate and replay held short-triplet likelihoods on six frozen offers."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import tracklet_triplets as model
from . import trackless_likelihood_trial as previous
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/support-preserving/tracklet-triplets"
world, shell = previous.world, previous.shell
PREDICTIONS = "positions.jsonl.gz"
WORKER = previous.WORKER.replace(
    "import trackless_likelihood as solver", "import tracklet_triplets as solver"
)


def run_offer(q, wave, cpu):
    start = perf_counter()
    capture = wave if q["cohort"] == "waveform" else world.clock.data(q, None)
    payload = encoded(dict(tile=q["tile"], capture=capture))
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(
        argv,
        [Path(model.__file__), Path(previous.model.__file__), Path(world.model.geodesy.__file__)],
    )
    try:
        p = subprocess.run(
            argv, input=payload, capture_output=True, check=True, timeout=shell.CAP_S
        )
        receipt = json.loads(p.stdout)
        if receipt["peak_rss_kib"] > shell.RSS:
            raise ValueError("worker exceeded memory bound")
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:]
        failure = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(err),
            boundary=model.BOUNDARY,
            metrics={"position_attempted": False},
            arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        )
        receipt = dict(result=[failure] * len(model.METHODS))
    elapsed = perf_counter() - start
    rows = []
    for method, result in zip(model.METHODS, receipt.pop("result"), strict=True):
        validate_result(result)
        print(
            q["id"],
            method,
            result["status"],
            result["reason"],
            result["metrics"].get("triplets"),
            round(elapsed, 2),
            flush=True,
        )
        rows.append(
            dict(
                q,
                method=method,
                result=result,
                **receipt,
                cpu=cpu,
                input_sha256=world.digest(payload),
                native_elapsed_s=elapsed,
            )
        )
    return rows


def run(work):
    work.mkdir(parents=True, mode=0o700)
    inherited_lock = previous.OUT / "prediction-lock.json"
    world.verify(previous.OUT, world.read(inherited_lock)["files"])
    offers = world.read(previous.OUT / "blind-plan.json")["cases"]
    supplied, wave = previous.waveform()
    if supplied != [q for q in offers if q["cohort"] == "waveform"] or len(offers) != 6:
        raise ValueError("the same four archive and two waveform requests are required")
    paths = [
        Path(model.__file__),
        Path(__file__),
        Path(previous.__file__),
        Path(previous.model.__file__),
        Path(shell.__file__),
        OUT / "PROTOCOL.md",
        inherited_lock,
        previous.WAVE / "detector-lock.json",
        *world.source_paths(),
    ]

    def hashes():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    pins = hashes()
    save_json(OUT / "source-lock.json", pins)
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=offers,
            sources=pins,
            cpus=list(shell.CPUS),
            cap_s=shell.CAP_S,
            memory_mib=512,
        ),
    )

    def lane(i):
        return [row for q in offers[i::2] for row in run_offer(q, wave, shell.CPUS[i])]

    with ThreadPoolExecutor(2) as pool:
        rows = [row for group in pool.map(lane, range(2)) for row in group]
    if pins != hashes():
        raise ValueError("triplet source changed during experiment")
    files = {
        name: world.digest((OUT / name).read_bytes())
        for name in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, rows)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in offers], files=files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)


if __name__ == "__main__":
    main()
