"""Seal, run and score a new multi-site native receiver transfer challenge."""

import argparse
import gzip
import json
import os
import secrets
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import joint_clock_model, joint_orbits, portable_v5, train_update
from . import generalization_challenge_scenes as scenes
from . import native_joint_trial as native
from .portable_gate_trials import checksum, compressed_rows, invoke

OUT = ROOT / "reports/2026_11_19_receiver_screening/refinement/region-challenge"
WORKER = Path(__file__).with_name("generalization_challenge_worker.py")
CLOCK = "native_joint_clock_model"
PREPARED = "prepared_joint_clock_model"
METHODS = (CLOCK, native.METHOD, train_update.METHOD)
QUERY_S = 32


def source():
    paths = [Path(__file__), WORKER, Path(native.__file__), Path(scenes.__file__)]
    paths += [
        Path(m.__file__)
        for m in (
            joint_clock_model,
            joint_orbits,
            train_update,
            portable_v5,
            scenes.cold,
            scenes.clock_model,
            scenes.perturb,
            scenes.samples,
            native.native,
            native.phase,
        )
    ]
    return dict(
        files={p.name: checksum(p) for p in paths},
        bundle={
            str(p.relative_to(native.BUNDLE)): checksum(p)
            for p in sorted(native.BUNDLE.rglob("*.py"))
        },
        donor_trace=checksum(scenes.samples.TRACE),
        donor_audit=checksum(scenes.samples.AUDIT),
        methods=[*METHODS, PREPARED],
        query_cap_s=QUERY_S,
    )


def command(cpu, files):
    argv = native.command(cpu, files, native.BUNDLE)
    argv[argv.index(str(native.WORKER))] = str(WORKER)
    for module in (joint_clock_model, train_update):
        path = Path(module.__file__)
        argv[-3:-3] = ["--ro-bind", str(path), f"/worker/tools/pipeline_eval/variants/{path.name}"]
    return argv


def bound(query, catalogue, collection, cfg):
    files = dict(native=query["native"], catalogue=catalogue, track_config=cfg)
    request = dict(
        mode="native",
        cutoff=query["cutoff"],
        catalog_timestamp=collection,
        probe_limit=query["probes"],
        offer=query["offer"],
        **{k: dict(path=f"/input/{k}", sha256=checksum(p)) for k, p in files.items()},
    )
    receipt = dict(
        id=query["id"],
        recording=query["capture"],
        tile=query["offer"],
        input_sha256=sha256(encoded(request)).hexdigest(),
        native_sha256=request["native"]["sha256"],
        catalog_sha256=request["catalogue"]["sha256"],
        track_config_sha256=request["track_config"]["sha256"],
        causal_history_sha256=sha256(encoded(query["history"])).hexdigest(),
        causal_history_count=len(query["history"]),
    )
    return request, files, receipt


def missing(status, reason):
    return dict(
        status=status,
        reason=reason,
        boundary="Synthetic native GLRT through frozen receiver",
        arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
        metrics={},
    )


def attempt(cpu, job, method, timeout):
    request, files, binding = job
    if timeout <= 0:
        return dict(binding, method=method, result=missing("missing", "wall budget not available"))
    out, err, status, elapsed = invoke(
        command(cpu, files), encoded(dict(method=method, request=request)), timeout
    )
    receipt = (
        json.loads(out)
        if status == "complete"
        else {
            "result": missing(status, err.decode(errors="replace")[-1800:] or "worker cap reached")
        }
    )
    validate_result(receipt["result"])
    print(binding["id"], method, receipt["result"]["status"], round(elapsed, 2), flush=True)
    return dict(binding, method=method, worker_wall_s=elapsed, cpu=cpu, **receipt)


def infer(work, report, cpus, seed_hex, budget):
    start = perf_counter()
    locked = source()
    save_json(report / "source-lock.json", locked)
    seed = bytes.fromhex(seed_hex) if seed_hex else secrets.token_bytes(32)
    queries, labels, catalogue, collection, audit = scenes.generate(seed, work)
    config = work / "graph-config.json"
    save_json(config, dict(config=portable_v5.TRACK_CONFIG))
    jobs = [bound(query, catalogue, collection, config) for query in queries]
    save_json(
        report / "input-lock.json",
        dict(
            manifest=[j[2] for j in jobs],
            history={q["capture"]: q["history"] for q in queries},
            source_sha256=checksum(report / "source-lock.json"),
            cpus=list(cpus),
            wall_cap_s=budget,
        ),
    )
    queue = deque(
        (job, METHODS[(i + k) % len(METHODS)])
        for i, job in enumerate(jobs)
        for k in range(len(METHODS))
    )
    guard = Lock()

    def lane(cpu):
        rows = []
        while True:
            with guard:
                if not queue:
                    return rows
                job, method = queue.popleft()
            remaining = budget - (perf_counter() - start)
            rows.append(attempt(cpu, job, method, min(QUERY_S, remaining - 4)))

    with ThreadPoolExecutor(len(cpus)) as pool:
        rows = [row for group in pool.map(lane, cpus) for row in group]
    if source() != locked:
        raise ValueError("the qualification source changed after freezing")
    rows.sort(key=lambda r: (r["id"], r["method"]))
    output = report / "raw-positions.jsonl.gz"
    write(output, compressed_rows(rows))
    save_json(
        report / "prediction-lock.json",
        dict(
            raw_sha256=checksum(output),
            input_sha256=checksum(report / "input-lock.json"),
            scheduled=len(jobs) * len(METHODS),
            elapsed_s=perf_counter() - start,
        ),
    )
    save_json(report / "labels.json", dict(seed_hex=seed.hex(), cases=labels, audit=audit))


def prepared(row):
    control = row.get("prepared_result")
    if control and row.get("prepared_equal") is not True:
        raise ValueError("native and prepared smooth-clock observations or endpoints differ")
    return dict(
        row,
        method=PREPARED,
        result=control or missing("missing", "no prepared parity result was available"),
        observation_sha256=row.get("prepared_projection_sha256"),
    )


def score(report):
    seal = json.loads((report / "prediction-lock.json").read_bytes())
    raw = report / "raw-positions.jsonl.gz"
    assert checksum(raw) == seal["raw_sha256"]
    assert checksum(report / "input-lock.json") == seal["input_sha256"]
    published = list(map(json.loads, gzip.decompress(raw.read_bytes()).splitlines()))
    labels = json.loads((report / "labels.json").read_bytes())["cases"]
    assert len(published) == len(labels) * len(METHODS) == seal["scheduled"]
    inventory, queries, rows = {}, [], []
    variants = [*published, *(prepared(r) for r in published if r["method"] == CLOCK)]
    for row in variants:
        label = labels[row["id"]]
        keys = ("input_sha256", "native_sha256", "catalog_sha256", "track_config_sha256")
        binding = {k: row[k] for k in keys}
        if row["id"] not in inventory:
            inventory[row["id"]] = binding
            queries.append(
                dict(
                    id=row["id"],
                    condition=label["condition"],
                    truth=label["truth"],
                    recording=f"Site {label['site']}" if label["site"] else "Lane shuffle",
                    bindings=binding,
                )
            )
        assert binding == inventory[row["id"]]
        result = row["result"]
        for arm, fit in result["arms"].items():
            rows.append(
                dict(
                    id=row["id"],
                    method=row["method"],
                    arm=arm,
                    site=label["site"],
                    condition=label["condition"],
                    boundary_clearance_km=label["boundary_clearance_km"],
                    status=result["status"],
                    reason=result.get("reason"),
                    published=fit["latlon"] is not None,
                    position_error_km=distance_km(label["truth"], fit["latlon"]),
                    forced_error_km=distance_km(label["truth"], fit.get("forced_latlon")),
                    conditional_rf_rms_hz=fit.get("rf_rms_hz"),
                    observation_sha256=row.get("observation_sha256"),
                    held_rms_hz=result["metrics"]
                    .get("held_by_arm", {})
                    .get(arm, {})
                    .get("held_rf_rms_hz"),
                    worker_wall_s=row.get("worker_wall_s") if row["method"] != PREPARED else None,
                )
            )
    groups = {}
    for row in rows:
        key = "/".join(row[k] for k in ("condition", "method", "arm"))
        groups.setdefault(key, []).append(row)
    totals = {
        key: dict(
            attempted=len(group),
            publications=sum(r["published"] for r in group),
            statuses=dict(Counter(r["status"] for r in group)),
            **{
                k: distribution(r[k] for r in group)
                for k in (
                    "position_error_km",
                    "forced_error_km",
                    "conditional_rf_rms_hz",
                    "held_rms_hz",
                    "worker_wall_s",
                )
            },
        )
        for key, group in groups.items()
    }
    for ident in inventory:
        projected = {
            r.get("observation_sha256")
            for r in variants
            if r["id"] == ident and r.get("observation_sha256")
        }
        assert len(projected) <= 1, ident
    save_json(report / "scores.json", dict(rows=rows, totals=totals))
    write(report / "positions.jsonl.gz", compressed_rows(variants))
    save_json(report / "figure-queries.json", dict(queries=queries))
    names = ("positions.jsonl.gz", "figure-queries.json")
    save_json(
        report / "figure-lock.json",
        dict(cases=list(inventory), files={n: checksum(report / n) for n in names}),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=OUT)
    parser.add_argument("--cpus", type=int, nargs=3, default=(0, 7, 17))
    parser.add_argument("--seed-hex")
    parser.add_argument("--budget-s", type=int, default=420)
    parser.add_argument("--score", action="store_true")
    args = parser.parse_args()
    work, report = local_output(args.work), local_output(args.report)
    if args.score:
        score(report)
    else:
        if len(set(args.cpus)) != 3 or not set(args.cpus) <= os.sched_getaffinity(0):
            parser.error("three distinct available CPUs required")
        work.mkdir(exist_ok=False, parents=True)
        infer(work, report, args.cpus, args.seed_hex, args.budget_s)


if __name__ == "__main__":
    main()
