"""Replay and independently score the fixed anonymous-track timing roster."""

import argparse
import gzip
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import ROOT, encoded, local_output, references, save_json, write
from ..reference import grid
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import projected_fit, robust_em
from .full_v5_check import _load_case
from .prefix_figures import TIMING_IDS, csv_file
from .rate_triplet_trials import WORKER as SANDBOX_WORKER
from .rate_triplet_trials import sandbox_command

WORKER = Path(__file__).with_name("robust_em_worker.py")
OUTPUT = ROOT / "reports/2026_11_19_short_receiver/robust-em"
WRONG_CASE = "DS26-0036"
WRONG_OFFER = "r0"
SOURCES = (Path(robust_em.__file__), Path(grid.__file__), Path(projected_fit.__file__), WORKER)
OBSERVATION_FIELDS = {
    "anchor_utc_ns",
    "duration_s",
    "catalog_timestamp_ns",
    "cutoff_utc_ns",
    "tracks",
}
TRACK_FIELDS = {"times", "values", "receiver", "channel", "rf_hz"}


def source_hashes():
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in SOURCES}


def load(case_id, mode, cache):
    case = _load_case(case_id)
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK))
    issues = {}
    if graph := case.get("graph"):
        source = corpus._locate(bulk, graph, "graph", issues)
        observation = corpus._observation(case, source, cache, issues) if source else None
    else:
        root = Path(os.environ.get("PIPELINE_EVAL_BLIND_ROOT", corpus.DEFAULT_BLIND))
        observation = corpus._portable_input(
            root / case["blind_tree"], cache, "observation", case["observation"], issues
        )
    catalogue = corpus._locate(bulk, case["catalog"], "catalogue", issues)
    if observation is None or catalogue is None:
        raise ValueError(f"frozen observations or catalogue are unavailable: {issues}")
    raw = observation.read_bytes()
    orbit = catalogue.read_bytes()
    data = json.loads(raw)
    if (
        set(data) != OBSERVATION_FIELDS
        or any(set(t) != TRACK_FIELDS for t in data["tracks"])
        or sha256(raw).hexdigest() != case["observation"]
        or sha256(orbit).hexdigest() != case["catalog"]["sha256"]
        or data["catalog_timestamp_ns"] != case["catalog_timestamp_ns"]
        or data["cutoff_utc_ns"] != case["cutoff_utc_ns"]
    ):
        raise ValueError("unexpected fields or provenance in frozen observations")
    if mode == "wrong-region":
        binding = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())[case_id]
        if (binding["observation_sha256"], binding["catalog_sha256"]) != (
            case["observation"],
            case["catalog"]["sha256"],
        ):
            raise ValueError("wrong-tile query has different observation/catalogue bindings")
        (offer,) = (r for r in binding["regions"] if r["id"] == WRONG_OFFER)
    else:
        (offer,) = case["regions"]
    return dict(observation=data, catalogue=orbit.decode("ascii"), offer=offer), dict(
        observation_sha256=case["observation"],
        catalogue_sha256=case["catalog"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        native_sha256=case["native"]["sha256"],
    )


def sandbox(cpu):
    command = sandbox_command(cpu)
    command[command.index(str(SANDBOX_WORKER))] = str(WORKER)
    packages = "/worker/tools/pipeline_eval"
    for module, package in (
        (robust_em, "variants"),
        (projected_fit, "variants"),
        (grid, "reference"),
    ):
        source = Path(module.__file__)
        command[-3:-3] = ["--ro-bind", str(source), f"{packages}/{package}/{source.name}"]
    return command


def run_one(job, *, cache, hashes, cpus):
    case, mode, slot = job
    cpu = cpus[slot]
    packet, bindings = load(case, mode, cache)
    payload = encoded(packet)
    started = perf_counter()
    try:
        proc = subprocess.run(
            sandbox(cpu), input=payload, capture_output=True, timeout=90, check=True
        )
        out = json.loads(proc.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        out = dict(
            worker_cpu_s=None,
            max_rss_kib=None,
            result=dict(
                status="failed" if isinstance(exc, subprocess.CalledProcessError) else "timed_out",
                boundary=robust_em.BOUNDARY,
                reason=(exc.stderr or b"").decode(errors="replace")[-1500:] or str(exc),
                metrics={},
                arms={arm: {"latlon": None} for arm in ARMS},
            ),
        )
    elapsed = perf_counter() - started
    validate_result(out["result"])
    row = dict(
        id=case,
        mode=mode,
        method=robust_em.METHOD,
        tile=packet["offer"],
        cpu=cpu,
        worker_wall_s=elapsed,
        implementation_sha256=hashes["robust_em.py"],
        input_sha256=sha256(payload).hexdigest(),
        **bindings,
        **out,
    )
    print(
        case,
        mode,
        row["result"]["status"],
        row["result"].get("reason"),
        round(elapsed, 2),
        row["max_rss_kib"],
        flush=True,
    )
    return row


def score(rows):
    refs = {}
    for panel, prefix in (("ds26-common127", "DS26"), ("roof16", "DS29")):
        ids = [row["id"] for row in rows if row["id"].startswith(prefix)]
        refs.update((r["id"], r) for r in references(panel, ids)[1])
    results = []
    for row in rows:
        ref, outcome = refs[row["id"]], row["result"]
        for arm in ARMS:
            fitted = outcome["arms"][arm]
            results.append(
                dict(
                    id=row["id"],
                    mode=row["mode"],
                    arm=arm,
                    result=outcome["status"],
                    reason=outcome.get("reason"),
                    error_km=distance_km(ref["truth"], fitted["latlon"]),
                    forced_error_km=distance_km(ref["truth"], fitted.get("forced_latlon")),
                    conditional_rms_hz=fitted.get("rf_rms_hz"),
                    frequency_score=fitted.get("frequency_score"),
                    original_v5_error_km=ref["reference"]["baseline"][arm]["error_km"],
                    max_rss_kib=row["max_rss_kib"],
                    worker_wall_s=row["worker_wall_s"],
                )
            )
    return results


def trial(output, cache, cpus):
    if len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose exactly two available logical CPUs")
    output, cache = local_output(output), local_output(cache)
    hashes = source_hashes()
    jobs = [(case, "matched-tile", i % 2) for i, case in enumerate(TIMING_IDS)]
    jobs.append((WRONG_CASE, "wrong-region", 0))
    run = partial(run_one, cache=cache, hashes=hashes, cpus=cpus)

    def lane(slot):
        return [run(job) for job in jobs if job[2] == slot]

    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = sorted(
            (row for items in pool.map(lane, range(2)) for row in items),
            key=lambda r: (r["mode"], TIMING_IDS.index(r["id"])),
        )
    if source_hashes() != hashes:
        raise ValueError("worker source changed during the replay")
    for mode, name in (("matched-tile", "positions"), ("wrong-region", "wrong-region")):
        data = b"".join(encoded(row) + b"\n" for row in rows if row["mode"] == mode)
        write(output / f"{name}.jsonl.gz", gzip.compress(data, mtime=0))
    save_json(output / "source-lock.json", hashes)
    scores = score(rows)
    csv_file(output / "scores.csv", scores)
    save_json(
        output / "summary.json",
        {
            arm: distribution(
                [r["error_km"] for r in scores if r["arm"] == arm and r["mode"] == "matched-tile"]
            )
            for arm in ARMS
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--cpus", nargs=2, type=int, default=(0, 1))
    args = parser.parse_args()
    trial(args.out, args.cache, args.cpus)


if __name__ == "__main__":
    main()
