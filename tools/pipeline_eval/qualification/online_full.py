"""Run the frozen smooth-clock policy causally until both arms have resolved."""

import argparse
import gzip
import json
import os
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS
from . import online_prefix as prefix
from . import online_prefix_trial as pilot
from .full_v5_check import BULK, _load_case
from .portable_gate_trials import checksum, compressed_rows

SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
OUT = SCREEN / "recovery/online-full"
ARCHIVE = SCREEN / "factors/native-clock-full"
COMPACT = SCREEN / "factors/full-comparison"
CLOSE = SCREEN / "recovery/exterior-evidence"
CPUS = (0, 1, 2, 3, 6, 8, 9, 10, 12)
SLICE_LOCK = Lock()


def read(path):
    return json.loads(path.read_bytes())


def sealed_rows(folder, seal_name, filename):
    seal = read(folder / seal_name)
    file = folder / filename
    if seal["files"][filename] != checksum(file):
        raise ValueError(f"archived full prediction digest changed for {filename}")
    return list(map(json.loads, gzip.decompress(file.read_bytes()).splitlines()))


def roster():
    existing = read(pilot.OUT / "source-lock.json")
    if pilot.source() != existing:
        raise ValueError("online-full policy differs from the sealed pilot")
    plan = read(ARCHIVE / "plan.json")
    source = plan["source"]
    deployed = pilot.native.NATIVE / "deployment.json"
    if (
        source["clock_solver"] != pilot.clock.CLOCK_SHA256
        or source["clock_selector"] != pilot.clock.WORKER_SHA256
        or source["deployment"] != checksum(deployed)
    ):
        raise ValueError("existing terminal receiver source differs from the prefix receiver")
    for target, record in read(deployed)["files"].items():
        path = pilot.native.BUNDLE / target.removeprefix("/worker/").removeprefix("/source/")
        assert checksum(path) == record["sha256"]
    old = {r["id"]: r for r in sealed_rows(ARCHIVE, "prediction-lock.json", "positions.jsonl.gz")}
    jobs = []
    for q in plan["cases"]:
        old_row = old[q["id"]]
        mode = "matched" if q["cohort"] == "roof" else "distant-omitted"
        jobs.append(
            dict(
                id=q["id"],
                recording=q["recording"],
                request=q["packet"],
                condition=mode,
                origin="native-clock-full",
                terminal=old_row,
            )
        )
    requests = read(CLOSE / "plan.json")
    assert requests["source"]["native_smooth"] == source
    for stage, bound in (("diagnostic-stress", "stress"), ("reserve", "reserve")):
        folder = CLOSE / stage
        draws = read(folder / "figure-queries.json")["queries"]
        wanted = {r["id"] for r in draws if r["condition"] == "near-outside"}
        # The authenticated chart binds the selection labels separately from the worker request.
        seal = read(folder / "figure-lock.json")
        assert seal["files"]["figure-queries.json"] == checksum(folder / "figure-queries.json")
        sealed = sealed_rows(folder, "prediction-lock.json", "native_joint_clock_model.jsonl.gz")
        close = {r["id"]: r for r in sealed if r["id"] in wanted}
        assert close.keys() == wanted
        for q in requests[bound]:
            if q["id"] in close:
                jobs.append(
                    dict(
                        id=q["id"],
                        recording=q["recording"],
                        request=q["packet"],
                        condition="near-omitted",
                        origin=f"exterior-evidence/{stage}",
                        terminal=close[q["id"]],
                    )
                )
    count = Counter(j["condition"] for j in jobs)
    assert count == {"matched": 135, "distant-omitted": 9, "near-omitted": 32}, count
    for j in jobs:
        q, t = j["request"], j["terminal"]
        assert t["method"] == pilot.clock.METHOD and q["mode"] == "native"
        assert t["input_sha256"] == sha256(encoded(q)).hexdigest() and t["tile"] == q["offer"]
        assert (
            t["native_sha256"] == q["native"]["sha256"]
            and t["catalog_sha256"] == q["catalogue"]["sha256"]
        )
    rank = {k: i for i, k in enumerate(("matched", "distant-omitted", "near-omitted"))}
    jobs.sort(key=lambda j: (rank[j["condition"]], j["id"]))
    return jobs


def snapshot_job(job, document, paths, horizon, staging):
    start = perf_counter()
    # The sealed pilot scopes its cutoff through one temporary module setting.
    with SLICE_LOCK:
        view, audit = prefix.snapshot(document, horizon)
    first_excluded = audit["first_noncausal_end_counter"]
    if audit["actual_last_sample_s"] > horizon or (
        not audit["uses_complete_capture"]
        and (
            first_excluded is None
            or first_excluded <= audit["first_counter"] + 10_000_000 * horizon
        )
    ):
        raise ValueError("the host sliced a different sample frontier")
    path = staging / "prefix.json"
    raw = encoded(view)
    write(path, raw)
    query = job["request"]
    request = dict(
        query,
        native=dict(path=query["native"]["path"], sha256=sha256(raw).hexdigest()),
        probe_limit=audit["expected_probes"],
    )
    data = encoded(request)
    binding = dict(
        id=job["id"],
        recording=job["recording"],
        condition=job["condition"],
        checkpoint=horizon,
        tile=query["offer"],
        native_sha256=query["native"]["sha256"],
        prefix_native_sha256=request["native"]["sha256"],
        catalog_sha256=query["catalogue"]["sha256"],
        track_config_sha256=query["track_config"]["sha256"],
        input_sha256=sha256(data).hexdigest(),
        capture=audit,
        staging_wall_s=perf_counter() - start,
    )
    return data, dict(paths, native=path), binding


def archive_terminal(job, paths, document):
    terminal = job["terminal"]
    with SLICE_LOCK:
        _, audit = prefix.snapshot(document, None)
    if terminal["result"]["status"] in {"ok", "withheld"}:
        counts = terminal["counts"]
        if (
            counts["probes"] != audit["expected_probes"]
            or counts["native_bytes"] != paths["native"].stat().st_size
        ):
            raise ValueError(
                "archived terminal did not consume the exact original capture frontier"
            )
    return dict(
        terminal,
        capture=audit,
        checkpoint="terminal",
        method="online-full-terminal",
        condition=job["condition"],
        source=job["origin"],
    )


def decision(rows, picked, arm):
    for i, (old, new) in enumerate(zip(rows, rows[1:], strict=False), 1):
        if prefix.agrees(old, new, arm)["agreement"]:
            picked.setdefault(arm, (i, "adjacent agreement"))
    if rows and rows[-1]["checkpoint"] == prefix.HORIZONS[-1]:
        picked.setdefault(arm, (len(rows) - 1, "ordinary deadline"))


def execute(job, cpu, work, remaining):
    item = _load_case(job["recording"])
    authority = dict(
        native=item["native"], catalogue=item["catalog"], track_config=item["track_config"]
    )
    paths = {k: BULK / v["path"] for k, v in authority.items()}
    assert all(checksum(p) == job["request"][k]["sha256"] for k, p in paths.items())
    doc = read(paths["native"])
    terminal = archive_terminal(job, paths, doc)
    rows, picked = [], {}
    with TemporaryDirectory(prefix=f"cpu-{cpu}-", dir=work) as scratch:
        for horizon in prefix.HORIZONS:
            if remaining() <= 0:
                break
            stage = snapshot_job(job, doc, paths, horizon, Path(scratch))
            rows.append(pilot.attempt(cpu, stage, min(pilot.CAP_S, remaining())))
            for arm in ARMS:
                decision(rows, picked, arm)
            if len(picked) == len(ARMS):
                break
    return dict(
        id=job["id"],
        recording=job["recording"],
        condition=job["condition"],
        terminal=terminal,
        rows=rows,
        picked=picked,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=OUT)
    parser.add_argument("--cpus", nargs="+", type=int, default=CPUS)
    parser.add_argument("--budget-s", type=int, default=700)
    args = parser.parse_args()
    start = perf_counter()
    if not {1, 10} <= set(args.cpus) <= os.sched_getaffinity(0) or len(set(args.cpus)) != len(
        args.cpus
    ):
        parser.error("use distinct authorized CPUs including 1 and 10")
    work, report = local_output(args.work), local_output(args.report)
    work.mkdir(exist_ok=False, parents=True)
    journal = work / "journal"
    journal.mkdir()
    jobs = roster()

    def lock():
        return dict(
            pilot=pilot.source(),
            runner=checksum(Path(__file__)),
            protocol=checksum(OUT / "PROTOCOL.md"),
        )

    sources = lock()
    save_json(report / "source-lock.json", sources)
    public = [{k: v for k, v in row.items() if k != "terminal"} for row in jobs]
    save_json(report / "plan.json", dict(jobs=public, cpus=args.cpus, budget_s=args.budget_s))
    queue, guard = deque(jobs), Lock()

    def remaining():
        return args.budget_s - (perf_counter() - start) - 5

    def lane(cpu):
        while remaining() > 0:
            with guard:
                if not queue:
                    return
                job = queue.popleft()
            try:
                result = execute(job, cpu, work, remaining)
            except (OSError, ValueError, AssertionError, KeyError) as exc:
                result = dict(
                    id=job["id"],
                    recording=job["recording"],
                    condition=job["condition"],
                    terminal=job["terminal"],
                    rows=[],
                    picked={},
                    error=str(exc) or type(exc).__name__,
                )
            save_json(journal / f"{job['id']}.json", result)

    with ThreadPoolExecutor(len(args.cpus)) as pool:
        list(pool.map(lane, args.cpus))
    if lock() != sources:
        raise ValueError("source changed after the run began")
    rows = []
    for job in jobs:
        receipt = journal / f"{job['id']}.json"
        rows.append(
            read(receipt)
            if receipt.exists()
            else dict(
                id=job["id"],
                recording=job["recording"],
                condition=job["condition"],
                terminal=job["terminal"],
                rows=[],
                picked={},
                missing=True,
            )
        )
    raw = report / "raw.jsonl.gz"
    write(raw, compressed_rows(rows))
    save_json(
        report / "prediction-lock.json",
        dict(
            raw_sha256=checksum(raw),
            plan_sha256=checksum(report / "plan.json"),
            cases=len(jobs),
            elapsed_s=perf_counter() - start,
            fresh_workers=sum(len(b["rows"]) for b in rows),
        ),
    )


if __name__ == "__main__":
    main()
