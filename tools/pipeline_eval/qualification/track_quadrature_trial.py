"""Lock, run and seal matched full, uniform and Lobatto orbit shortlist replays."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, validate_result
from .broad_search_budget import frozen_inputs
from .fresh_scenes import _read, _sha

REPORT = ROOT / "reports/2026_11_19_receiver_screening/native-receiver/track-quadrature"
SUPPORT = REPORT.parent.parent / "factors/native-full"
CAP_S = 180
CPUS = (14, 15)
SEED = "track-quadrature-20261120-v1:"
METHODS = ("all_samples", "uniform_samples", "track_quadrature")
POSITIONS = "positions.jsonl.gz"
WORKER = "tools.pipeline_eval.qualification.track_quadrature_worker"
ENV = {
    k: "1"
    for k in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")
}


def source_files():
    source = ROOT / "src/leo"
    tool = ROOT / "tools/pipeline_eval"
    paths = [
        Path(__file__),
        tool / "qualification/track_quadrature_worker.py",
        REPORT / "PROTOCOL.md",
        tool / "reference/grid.py",
        tool / "reference/native_archive.py",
        *(
            tool / "variants" / f"{name}.py"
            for name in (
                "track_quadrature",
                "joint_orbits",
                "native_lean",
                "robust_orbit_fit",
                "robust_em",
                "projected_fit",
            )
        ),
        *(
            source / "analysis" / f"{name}.py"
            for name in (
                "graph_tracklets",
                "polynomial_tracklets",
                "tracklet_fitting",
            )
        ),
        *(source / "sky" / f"{name}.py" for name in ("propagation", "frames")),
        corpus.FROZEN / "provenance.json",
        SUPPORT / "prediction-lock.json",
    ]
    return {str(p.relative_to(ROOT)): _sha(p) for p in paths}


def inventory(inputs):
    archive = SUPPORT / POSITIONS
    if _sha(archive) != _read(SUPPORT / "prediction-lock.json")["files"][POSITIONS]:
        raise ValueError("original support census checksum changed")
    counts = {}
    with gzip.open(archive, "rt") as stream:
        for raw in stream:
            record = json.loads(raw)
            ident = record["id"]
            if ident not in inputs:
                continue
            item = inputs[ident]
            if (record["native_sha256"], record["catalog_sha256"], [record["tile"]]) != (
                item["native"]["sha256"],
                item["catalog"]["sha256"],
                item["regions"],
            ):
                raise ValueError(f"unmatched support census for {ident}")
            metrics = record["result"]["metrics"]
            if metrics.get("input_tracks", 0) > 0:
                counts[ident] = {k: metrics[k] for k in ("input_points", "input_tracks")}
                counts[ident]["observation_sha256"] = record["observation_sha256"]
    return counts


def choose(inputs, counts):
    """Choose a dense, a short, and an unstratified capture per dataset."""
    selected = []
    for dataset in ("DS26", "DS29"):
        ids = {i for i in counts if i.startswith(dataset + "-")}
        size = max(1, len(ids) // 3)
        short = sorted(
            ids, key=lambda i: (counts[i]["input_points"] / counts[i]["input_tracks"], i)
        )[:size]
        dense = sorted(ids, key=lambda i: (-counts[i]["input_points"], i))[:size]
        chosen = set()
        for stratum, pool in (("dense", dense), ("short", short), ("unstratified", ids)):
            pick = min(
                set(pool) - chosen,
                key=lambda i: sha256((SEED + inputs[i]["native"]["sha256"]).encode()).digest(),
            )
            selected.append((pick, stratum))
            chosen.add(pick)
    return selected


def packet(item):
    bulk = Path(os.environ.get("PIPELINE_EVAL_BULK_ROOT", corpus.DEFAULT_BULK))
    (offer,) = item["regions"]
    assert item["catalog_timestamp_ns"] <= item["cutoff_utc_ns"]
    request = dict(
        mode="native",
        cutoff=item["cutoff_utc_ns"],
        offer=offer,
        catalog_timestamp=item["catalog_timestamp_ns"],
        probe_limit=2 * item["recording"]["window_count"],
    )
    for field, label in (
        ("catalog", "catalogue"),
        ("native", "native"),
        ("track_config", "track_config"),
    ):
        bound = item[field]
        request[label] = dict(path=str(bulk / bound["path"]), sha256=bound["sha256"])
    return request


def freeze(work):
    work.mkdir(parents=True, exist_ok=False)
    inputs = frozen_inputs()
    counts = inventory(inputs)
    jobs = []
    for index, (ident, stratum) in enumerate(choose(inputs, counts)):
        order = METHODS[index % 3 :] + METHODS[: index % 3]
        if index >= 3:
            order = order[::-1]
        jobs.append(
            dict(
                id=ident,
                stratum=stratum,
                **counts[ident],
                packet=packet(inputs[ident]),
                cpu=CPUS[index % 2],
                order=order,
            )
        )
    save_json(
        work / "source-lock.json",
        dict(
            seed=SEED,
            source=source_files(),
            jobs=jobs,
            census_size=len(counts),
            address_space_mib=512,
            timeout_s=CAP_S,
            numerical_threads=1,
        ),
    )


def attempt(job, method):
    request = job["packet"]
    started = perf_counter()
    try:
        launched = subprocess.run(
            ("taskset", "-c", str(job["cpu"]), sys.executable, "-m", WORKER),
            cwd=ROOT,
            input=encoded(dict(request, method=method)),
            capture_output=True,
            check=True,
            timeout=CAP_S,
            env=os.environ | ENV,
        )
        out = json.loads(launched.stdout)
        if out["observation_sha256"] != job["observation_sha256"]:
            raise RuntimeError(
                f"{job['id']} differs from the authenticated original Graph projection"
            )
    except (OSError, subprocess.SubprocessError, ValueError) as err:
        reason = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1800:] or str(err)
        out = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=reason,
                boundary="Stored original GLRT peaks through native joint positioning",
                metrics={},
                arms={a: dict(latlon=None) for a in ARMS},
            )
        )
    validate_result(out["result"])
    out.update(
        id=job["id"],
        method=method,
        cpu=job["cpu"],
        stratum=job["stratum"],
        tile=request["offer"],
        input_sha256=sha256(encoded(request)).hexdigest(),
        native_sha256=request["native"]["sha256"],
        catalog_sha256=request["catalogue"]["sha256"],
        worker_wall_s=perf_counter() - started,
    )
    print(job["id"], method, out["result"]["status"], round(out["worker_wall_s"], 3), flush=True)
    return out


def predict(work, output):
    manifest = work / "source-lock.json"
    lock = _read(manifest)
    jobs = lock["jobs"]
    if lock["source"] != source_files() or not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("locked source or dedicated fit core is unavailable")
    journal = work / "predictions"
    journal.mkdir()

    def lane(cpu):
        for job in jobs:
            if job["cpu"] == cpu:
                for method in job["order"]:
                    save_json(journal / f"{job['id']}-{method}.json", attempt(job, method))

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, CPUS))
    if lock["source"] != source_files():
        raise ValueError("locked source changed while inference ran")
    rows = [_read(journal / f"{job['id']}-{m}.json") for job in jobs for m in METHODS]
    write(
        output / POSITIONS, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)
    )
    write(output / manifest.name, manifest.read_bytes())
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=[job["id"] for job in jobs],
            files={
                POSITIONS: _sha(output / POSITIONS),
                manifest.name: _sha(output / manifest.name),
            },
        ),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("lock", "predict"))
    cli.add_argument("work", type=local_output)
    cli.add_argument("--output", type=local_output, default=REPORT)
    args = cli.parse_args()
    if args.action == "lock":
        freeze(args.work)
    else:
        predict(args.work, args.output)


if __name__ == "__main__":
    main()
