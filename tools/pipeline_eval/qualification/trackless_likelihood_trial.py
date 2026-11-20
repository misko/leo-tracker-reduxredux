"""Replay a bounded trackless GLRT likelihood on roof and emitted-waveform inputs."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import trackless_likelihood as model
from . import doppler_turns_trial as shell
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-frontier/trackless-likelihood"
WAVE = OUT.parent.parent / "track-recovery/waveform-site"
world = shell.world
PREDICTIONS = "positions.jsonl.gz"
ROOF = ("DS26-0261", "DS29-0519")
WORKER = shell.WORKER.replace(
    "import doppler_turns as solver", "import trackless_likelihood as solver"
).replace(
    "result = solver.measure(capture, q['tile'])", "result = solver.evaluate(capture, q['tile'])"
)


def waveform():
    receipt = world.read(WAVE / "detector-lock.json")
    world.verify(WAVE, receipt["files"])
    world.verify(WAVE, world.read(WAVE / "input-lock.json")["files"])
    if not receipt["ready"] or (receipt["scheduled_visits"], receipt["completed_visits"]) != (
        1200,
        1200,
    ):
        raise ValueError("the emitted waveform native detector is incomplete")
    native = gzip.decompress((WAVE / "native.json.gz").read_bytes())
    doc = json.loads(native)
    source, clock = doc["source"], doc["clock_anchor"]
    before, after = [clock[k]["realtime_ns"] for k in ("before", "after")]
    catalogue, collected = world.synthetic._catalogue()
    catalogue_sha = world.digest(catalogue)
    witnesses = [
        q
        for q in world.read(WAVE / "causal-authority.json").values()
        if (q["sha256"], q["collected_utc_ns"]) == (catalogue_sha, collected)
    ]
    if not source["qualified"] or not collected <= before <= after or len(witnesses) != 1:
        raise ValueError("the waveform clock or causal catalogue cannot be authenticated")
    queries = []
    for q in world.read(WAVE / "requests.json"):
        if (q["session"], q["native_sha256"], q["catalog_sha256"]) != (
            source["session_id"],
            world.digest(native),
            catalogue_sha,
        ):
            raise ValueError("waveform offer differs from the frozen detector output")
        queries.append(
            dict(
                id=q["id"],
                recording=q["session"],
                cohort="waveform",
                tile=dict(center=q["tile"], width_km=25),
                native_sha256=q["native_sha256"],
                catalog_sha256=q["catalog_sha256"],
                original_request_sha256=world.digest(encoded(q)),
                cutoff=before,
                collected=collected,
            )
        )
    first = clock["sample_counter"]
    rate = source["sample_rate_hz"]
    capture = dict(
        case_id=source["session_id"],
        probes=source["probes"],
        sample_rate_hz=rate,
        probe_ms=source["probe_ms"],
        first_counter=first,
        anchor_utc_ns=(before + after) // 2,
        cutoff_utc_ns=before,
        catalog_timestamp_ns=collected,
        duration_s=(doc["last_sample_counter"] - first) / rate,
        catalog=catalogue.decode("ascii"),
    )
    return queries, capture


def attempt(q, wave, cpu):
    start = perf_counter()
    capture = wave if q["cohort"] == "waveform" else world.clock.data(q, None)
    payload = encoded(dict(tile=q["tile"], capture=capture))
    prior = world.prior
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(argv, [Path(model.__file__), Path(world.model.geodesy.__file__)])
    try:
        p = subprocess.run(
            argv, input=payload, capture_output=True, check=True, timeout=shell.CAP_S
        )
        worker = json.loads(p.stdout)
        if worker["peak_rss_kib"] > shell.RSS:
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
        worker = dict(result=[failure] * len(model.METHODS))
    elapsed = perf_counter() - start
    rows = []
    for method, result in zip(model.METHODS, worker.pop("result"), strict=True):
        validate_result(result)
        print(
            q["id"],
            method,
            result["status"],
            result["reason"],
            result["metrics"].get("slices"),
            round(elapsed, 2),
            flush=True,
        )
        rows.append(
            dict(
                q,
                method=method,
                result=result,
                **worker,
                cpu=cpu,
                input_sha256=world.digest(payload),
                native_elapsed_s=elapsed,
            )
        )
    return rows


def run(work):
    work.mkdir(parents=True, mode=0o700)
    paths = [
        Path(model.__file__),
        Path(__file__),
        Path(shell.__file__),
        OUT / "PROTOCOL.md",
        *world.source_paths(),
        world.OUT / "prediction-lock.json",
        WAVE / "detector-lock.json",
    ]

    def hashes():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in paths}

    sources = hashes()
    save_json(OUT / "source-lock.json", sources)
    frames, wave = waveform()
    queries = [
        q for q in shell.regional.inputs() if q["id"] in ROOF or q["cohort"] == "omitted"
    ] + frames
    if len(queries) != 6:
        raise ValueError("expected two real containing, two real omitted and two waveform offers")
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=sources,
            cpus=list(shell.CPUS),
            cap_s=shell.CAP_S,
            memory_mib=512,
        ),
    )

    def lane(i):
        return [row for q in queries[i::2] for row in attempt(q, wave, shell.CPUS[i])]

    with ThreadPoolExecutor(2) as pool:
        rows = [row for group in pool.map(lane, range(2)) for row in group]
    if sources != hashes():
        raise ValueError("trackless source changed during trial")
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
