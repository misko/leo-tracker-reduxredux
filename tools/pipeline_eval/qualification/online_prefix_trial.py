"""Qualify actual smooth-clock work on independently sliced native acquisition prefixes."""

import argparse
import gzip
import json
import os
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from threading import Lock
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import joint_clock_model
from . import native_clock_full as clock
from . import native_joint_trial as native
from . import online_prefix as prefix
from .full_v5_check import BULK, FROZEN, _load_case
from .portable_gate_trials import checksum, compressed_rows, invoke
from .prefix_figures import TIMING_IDS

OUT = ROOT / "reports/2026_11_19_receiver_screening/recovery/online-prefix"
WORKER = Path(__file__).with_name("online_prefix_worker.py")
CASES = (*TIMING_IDS, "DS26-0261", "DS29-0357")
WRONG = ("DS26-0036", "DS29-0357")
CHECKPOINTS = (*prefix.HORIZONS, "terminal")
CAP_S = 35
BOUNDARY = "Independent acquisition prefixes through the ordinary native smooth-clock receiver"


def source():
    paths = [
        Path(__file__),
        WORKER,
        Path(prefix.__file__),
        Path(prefix.contiguous_prefix.__file__),
        Path(joint_clock_model.__file__),
        clock.WORKER,
        Path(native.__file__),
    ]
    if checksum(paths[4]) != clock.CLOCK_SHA256 or checksum(clock.WORKER) != clock.WORKER_SHA256:
        raise ValueError("online receiver differs from the locked smooth-clock implementation")
    return dict(
        files={p.name: checksum(p) for p in paths},
        bundle={
            str(p.relative_to(native.BUNDLE)): checksum(p)
            for p in sorted(native.BUNDLE.rglob("*.py"))
        },
        roster=list(CASES),
        omitted=list(WRONG),
        checkpoints=list(CHECKPOINTS),
        cap_s=CAP_S,
        protocol_sha256=checksum(OUT / "PROTOCOL.md"),
        policy=dict(
            max_distance_km=prefix.MAX_DISAGREEMENT_KM,
            min_shared_orbits=prefix.MIN_SHARED_ORBITS,
            min_refreshed_orbits=prefix.MIN_FRESH_ORBITS,
        ),
    )


def control_offers(items):
    omitted = {}
    original = json.loads((FROZEN / "roof-four-offers.json").read_bytes())[WRONG[0]]
    assert original["catalog_sha256"] == items[WRONG[0]]["catalog"]["sha256"]
    (omitted[WRONG[0]],) = [o for o in original["regions"] if o["id"] == "r0"]
    prior = ROOT / "reports/2026_11_19_receiver_screening/lean-support"
    raw = prior / "predictions.jsonl.gz"
    lock = json.loads((prior / "prediction-lock.json").read_bytes())
    assert checksum(raw) == lock["files"][raw.name]
    with gzip.open(raw, "rt") as handle:
        (row,) = [
            r
            for r in map(json.loads, handle)
            if (r["id"], r["method"], r["mode"]) == (WRONG[1], "robust_support", "wrong-region")
        ]
    assert row["native_sha256"] == items[WRONG[1]]["native"]["sha256"]
    assert row["catalog_sha256"] == items[WRONG[1]]["catalog"]["sha256"]
    omitted[WRONG[1]] = row["tile"]
    return omitted


def prepare(work):
    items = {i: _load_case(i) for i in CASES}
    wrong = control_offers(items)
    jobs = []
    for ident, item in items.items():
        locators = dict(
            native=item["native"], track_config=item["track_config"], catalogue=item["catalog"]
        )
        files = {k: BULK / v["path"] for k, v in locators.items()}
        assert all(checksum(p) == locators[k]["sha256"] for k, p in files.items())
        document = json.loads(files["native"].read_bytes())
        (original,) = item["regions"]
        offered = {"matched": original}
        if ident in wrong:
            offered["omitted"] = wrong[ident]
        for horizon in CHECKPOINTS:
            start = perf_counter()
            view, audit = prefix.snapshot(document, None if horizon == "terminal" else horizon)
            path = work / f"{ident}-{horizon}.json"
            write(path, encoded(view))
            preparation_s = perf_counter() - start
            inputs = dict(files, native=path)
            digest = checksum(path)
            bound = {
                k: dict(path=f"/input/{k}", sha256=digest if k == "native" else v["sha256"])
                for k, v in locators.items()
            }
            for condition, offer in offered.items():
                request = dict(
                    mode="native",
                    cutoff=item["cutoff_utc_ns"],
                    catalog_timestamp=item["catalog_timestamp_ns"],
                    probe_limit=audit["expected_probes"],
                    offer=offer,
                    **bound,
                )
                body = encoded(request)
                receipt = dict(
                    id=f"{ident}-{condition}",
                    recording=ident,
                    condition=condition,
                    checkpoint=horizon,
                    tile=offer,
                    native_sha256=item["native"]["sha256"],
                    prefix_native_sha256=digest,
                    catalog_sha256=item["catalog"]["sha256"],
                    track_config_sha256=item["track_config"]["sha256"],
                    input_sha256=sha256(body).hexdigest(),
                    capture=audit,
                    staging_wall_s=preparation_s,
                )
                jobs.append((body, inputs, receipt))
    return jobs


def attempt(cpu, job, timeout):
    packet, paths, binding = job
    command = clock.command(cpu, paths, native.BUNDLE)
    command[command.index(str(clock.WORKER))] = str(WORKER)
    command[-3:-3] = [
        "--ro-bind",
        str(clock.WORKER),
        "/worker/tools/pipeline_eval/qualification/native_clock_model_worker.py",
    ]
    out, err, status, wall = (
        invoke(command, packet, timeout)
        if timeout > 0
        else (b"", b"budget expired before launch", "missing", None)
    )
    if status == "complete":
        result = json.loads(out)
        audit = binding["capture"]
        if (
            result["counts"]["probes"] != audit["expected_probes"]
            or result["latest_graph_time_s"] > audit["actual_last_sample_s"]
            or any(
                row["latest_s"] > audit["actual_last_sample_s"]
                for arm in result["orbit_support"].values()
                for row in arm.values()
            )
        ):
            raise ValueError("native or Graph support exceeds the declared prefix")
    else:
        result = dict(
            result=dict(
                status=status,
                reason=err.decode(errors="replace")[-1800:] or "worker wall cap reached",
                boundary=BOUNDARY,
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
                metrics={},
            )
        )
    validate_result(result["result"])
    print(binding["id"], binding["checkpoint"], result["result"]["status"], wall, flush=True)
    return dict(
        binding,
        **result,
        cpu=cpu,
        worker_wall_s=wall,
        method=f"native-clock-{binding['checkpoint']}",
    )


def infer(work, report, cpus, budget):
    start = perf_counter()
    locked = source()
    save_json(report / "source-lock.json", locked)
    jobs = prepare(work)
    save_json(
        report / "input-lock.json", dict(jobs=[r for _, _, r in jobs], cpus=cpus, budget_s=budget)
    )
    queue, guard = deque(jobs), Lock()

    def lane(cpu):
        rows = []
        while True:
            with guard:
                if not queue:
                    return rows
                job = queue.popleft()
            rows.append(attempt(cpu, job, min(CAP_S, budget - (perf_counter() - start) - 5)))

    with ThreadPoolExecutor(2) as pool:
        rows = [r for group in pool.map(lane, cpus) for r in group]
    if locked != source():
        raise ValueError("measured receiver source changed during the replay")
    raw = report / "raw-prefixes.jsonl.gz"
    write(
        raw,
        compressed_rows(sorted(rows, key=lambda r: (r["id"], CHECKPOINTS.index(r["checkpoint"])))),
    )
    save_json(
        report / "prediction-lock.json",
        dict(
            raw_sha256=checksum(raw),
            input_sha256=checksum(report / "input-lock.json"),
            scheduled=len(jobs),
            measured_wall_s=perf_counter() - start,
        ),
    )


def frozen_truth():
    path = FROZEN / "targets.jsonl"
    expected = json.loads((FROZEN / "provenance.json").read_bytes())["files"][path.name]
    assert checksum(path) == expected
    return {row["id"]: row["truth"] for row in map(json.loads, path.read_bytes().splitlines())}


def stop_rows(rows):
    schedule = [row for row in rows if row["checkpoint"] != "terminal"]
    terminal = rows[-1]
    arrival = prefix.timeline(schedule)
    policy, arms = {}, {}
    for arm in ARMS:
        i, reason, pairs = prefix.stable_stop(schedule, arm)
        chosen = schedule[i]
        arms[arm] = chosen["result"]["arms"][arm]
        policy[arm] = dict(
            checkpoint=chosen["checkpoint"],
            reason=reason,
            pairs=pairs,
            original_status=chosen["result"]["status"],
            elapsed_host_s=arrival[i],
            prefix_workers_wall_s=sum(r["worker_wall_s"] or 0 for r in schedule[: i + 1]),
            prefix_workers_cpu_s=sum(
                r.get("worker", {}).get("cpu_s", 0) for r in schedule[: i + 1]
            ),
            terminal_only_elapsed_host_s=[
                a + terminal["worker_wall_s"] for a in terminal["capture"]["available_at_elapsed_s"]
            ]
            if terminal.get("worker_wall_s") is not None
            else None,
        )
    status = (
        "ok"
        if any(a["latlon"] is not None for a in arms.values())
        else schedule[-1]["result"]["status"]
    )
    reason = (
        None
        if status == "ok"
        else schedule[-1]["result"].get("reason") or "ordinary deadline withheld"
    )
    result = dict(status=status, reason=reason, boundary=BOUNDARY, arms=arms, metrics=policy)
    validate_result(result)
    shared = {
        k: terminal[k]
        for k in (
            "id",
            "recording",
            "condition",
            "tile",
            "native_sha256",
            "catalog_sha256",
            "track_config_sha256",
        )
    }
    return dict(shared, method="native-clock-stable-stop", result=result)


def score(report):
    lock = json.loads((report / "prediction-lock.json").read_bytes())
    raw = report / "raw-prefixes.jsonl.gz"
    assert (
        checksum(raw) == lock["raw_sha256"]
        and checksum(report / "input-lock.json") == lock["input_sha256"]
    )
    rows = list(map(json.loads, gzip.decompress(raw.read_bytes()).splitlines()))
    assert len(rows) == lock["scheduled"] == 50
    truth = frozen_truth()
    groups = defaultdict(list)
    for r in rows:
        groups[r["id"]].append(r)
    queries, policies, scored = [], [], []
    for ident, group in groups.items():
        site = truth[group[0]["recording"]]
        assert [r["checkpoint"] for r in group] == list(CHECKPOINTS)
        policy = stop_rows(group)
        policies.append(policy)
        representative = group[0]
        bindings = {
            k: representative[k] for k in ("native_sha256", "catalog_sha256", "track_config_sha256")
        }
        queries.append(
            dict(
                id=ident,
                recording=representative["recording"],
                truth=site,
                condition=representative["condition"],
                bindings=bindings,
            )
        )
        scenario = prefix.timeline(group[:-1])
        for i, row in enumerate([*group, policy]):
            result = row["result"]
            for arm, fit in result["arms"].items():
                policy_details = result["metrics"][arm] if row is policy else {}
                time = scenario[i] if i < len(scenario) else None
                scored.append(
                    dict(
                        id=ident,
                        recording=row["recording"],
                        condition=row["condition"],
                        method=row["method"],
                        arm=arm,
                        checkpoint=row.get("checkpoint", policy_details.get("checkpoint")),
                        status=result["status"],
                        published=fit["latlon"] is not None,
                        reason=result.get("reason"),
                        position_error_km=distance_km(fit["latlon"], site),
                        forced_error_km=distance_km(fit.get("forced_latlon"), site),
                        rf_rms_hz=fit.get("rf_rms_hz"),
                        worker_wall_s=row.get("worker_wall_s"),
                        elapsed_host_s=policy_details.get("elapsed_host_s", time),
                        policy=policy_details,
                    )
                )
    summary = defaultdict(list)
    for r in scored:
        summary["/".join(r[k] for k in ("method", "condition", "arm"))].append(r)
    save_json(
        report / "scores.json",
        dict(
            rows=scored,
            totals={
                k: dict(
                    attempts=len(g),
                    published=sum(r["published"] for r in g),
                    status=dict(Counter(r["status"] for r in g)),
                    **{
                        f: distribution(r[f] for r in g)
                        for f in ("position_error_km", "rf_rms_hz", "worker_wall_s")
                    },
                )
                for k, g in summary.items()
            },
        ),
    )
    names = ("positions.jsonl.gz", "figure-queries.json")
    write(report / names[0], compressed_rows([*rows, *policies]))
    save_json(report / names[1], dict(queries=queries))
    save_json(
        report / "figure-lock.json",
        dict(cases=list(groups), files={n: checksum(report / n) for n in names}),
    )


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=Path, required=True)
    cli.add_argument("--report", type=Path, default=OUT)
    cli.add_argument("--cpus", type=int, nargs=2, default=(1, 10))
    cli.add_argument("--budget-s", type=int, default=420)
    cli.add_argument("--score", action="store_true")
    arg = cli.parse_args()
    work, report = local_output(arg.work), local_output(arg.report)
    if arg.score:
        score(report)
    else:
        if len(set(arg.cpus)) != 2 or not set(arg.cpus) <= os.sched_getaffinity(0):
            cli.error("two distinct available CPUs required")
        work.mkdir(exist_ok=False, parents=True)
        infer(work, report, arg.cpus, arg.budget_s)


if __name__ == "__main__":
    main()
