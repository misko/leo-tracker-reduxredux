"""Run and seal blind native phase-support qualification against archived stock joint."""

import argparse
import gzip
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..corpus import _selection
from ..scoring import ARMS, validate_result
from . import native_joint_full as panel
from .full_v5_check import BULK

base = panel.base
REPORT = ROOT / "reports/2026_11_19_receiver_screening/refinement/phase-support"
WORKER = Path(__file__).with_name("phase_support_worker.py")
CPUS = (12, 13, 14, 15)
CAP = 45
DISPUTED = ("DS26-0223", "DS26-0197", "DS29-0316", "DS26-0036")
EXCLUDED = set(DISPUTED) | {"DS26-0243", "DS26-0287", "DS26-0237", "DS26-0299"}
OMITTED = ("DS26-0203-omitted", "DS29-0316-omitted")
SNAPSHOT = re.compile(r"([0-9]+)-([a-f0-9]{64})\.tle")
HISTORY_NS = 72 * 3600 * 10**9


def digest(data):
    return sha256(data).hexdigest()


def history_paths(item):
    raw = (BULK / item["request"]["path"]).read_bytes()
    if digest(raw) != item["request"]["sha256"]:
        raise ValueError("original causal history manifest changed")
    request = json.loads(raw)
    original = request["job"]
    stamp, limit = item["catalog_timestamp_ns"], item["cutoff_utc_ns"]
    current = item["catalog"]["sha256"]
    if (
        original["evaluation_reference"] is not None
        or stamp > limit
        or (request["causal_snapshots"].get(f"{stamp}-{current}.tle") != current)
    ):
        raise ValueError("the current light catalogue has no frozen collection authority")
    sources = []
    for name, checksum in request["causal_snapshots"].items():
        match = SNAPSHOT.fullmatch(name)
        if not match or checksum != match[2] or int(match[1]) > limit:
            raise ValueError("a manifest names a malformed or future element snapshot")
        collected = int(match[1])
        if limit - HISTORY_NS <= collected < stamp and checksum != current:
            path = Path(original["tle_root"]) / "archive" / "space-track" / name
            sources.append((collected, checksum, path))
    files, records, seen = {}, [], set()
    for collected, checksum, path in sorted(sources, reverse=True):
        if checksum in seen or not path.is_file():
            continue
        slot = f"history-{len(records)}.tle"
        records.append(dict(collection_ns=collected, sha256=checksum, path=f"/input/{slot}"))
        files[slot] = path
        seen.add(checksum)
    return records, files


def setup(full, bundle):
    inputs = base.phase.frozen_inputs()
    candidates = set(_selection("ds26-common127")[0]) - set(_selection("roof16")[0]) - EXCLUDED
    candidate_ids = sorted(
        (
            i
            for i in candidates
            if all(inputs[i].get(k) for k in ("recording", "request", "catalog"))
        ),
        key=lambda i: digest(("native-phase-support-confirm-v1:" + i).encode()),
    )[:4]
    primary = (*DISPUTED, *candidate_ids)
    omitted = dict((row["id"], (row, paths)) for row, paths in panel.omitted_controls(inputs))
    core = [
        (panel.query(inputs[i], "disputed" if i in DISPUTED else "confirmation"), "causal")
        for i in primary
    ]
    core.extend((omitted[i], "causal") for i in OMITTED)
    core.extend(
        (panel.query(inputs[i], "disputed"), p) for i in DISPUTED for p in ("fixed", "wide")
    )
    core.extend((omitted[i], "wide") for i in OMITTED)
    if full:
        core.extend(
            (panel.query(inputs[i], "roof"), "causal") for i in sorted(inputs) if i not in primary
        )
        core.extend((job, "causal") for i, job in omitted.items() if i not in OMITTED)
    base_source = base.sources(bundle)
    paths = [
        Path(__file__),
        WORKER,
        REPORT / "PROTOCOL.md",
        *(
            ROOT / f"tools/pipeline_eval/variants/{n}.py"
            for n in ("phase_support", "phase_support_history")
        ),
    ]
    source = dict(
        stock=base_source,
        files={str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in paths},
        stock_positions_sha256=digest((panel.REPORT / "positions.jsonl.gz").read_bytes()),
    )
    return (
        inputs,
        core,
        dict(
            source=source,
            primary=primary,
            confirmation=candidate_ids,
            omitted=OMITTED,
            full_requested=full,
            scheduled=[dict(id=q["id"], policy=policy) for (q, _), policy in core],
        ),
    )


def command(cpu, paths, bundle):
    argv = base.command(cpu, paths, bundle)
    argv[argv.index(str(base.WORKER))] = str(WORKER)
    for name in ("phase_support", "phase_support_history"):
        argv[-3:-3] = [
            "--ro-bind",
            str(ROOT / f"tools/pipeline_eval/variants/{name}.py"),
            f"/worker/tools/pipeline_eval/variants/{name}.py",
        ]
    return argv


def attempt(query, paths, policy, item, cpu, bundle):
    began = perf_counter()
    packet = query["packet"]
    files, entries = {}, []
    try:
        if policy == "causal":
            entries, files = history_paths(item)
        request = encoded(dict(packet, phase_support_policy=policy, phase_history=entries))
        child = subprocess.run(
            command(cpu, paths | files, bundle),
            input=request,
            capture_output=True,
            timeout=CAP,
            check=True,
        )
        result = json.loads(child.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        reason = (getattr(exc, "stderr", None) or b"").decode(errors="replace")[-1500:] or str(exc)
        status = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
        result = dict(
            result=dict(
                status=status,
                reason=reason,
                boundary="native phase support",
                metrics={},
                arms={arm: dict(latlon=None) for arm in ARMS},
            )
        )
    validate_result(result["result"])
    return dict(
        **{k: v for k, v in query.items() if k != "packet"},
        **result,
        method="phase_support_" + policy,
        policy=policy,
        cpu=cpu,
        input_sha256=digest(encoded(packet)),
        history_sha256=digest(encoded(entries)),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        tile=packet["offer"],
        worker_wall_s=perf_counter() - began,
    )


def run(work, full, seconds):
    started = perf_counter()
    work.mkdir(parents=True, exist_ok=False)
    bundle = base.BUNDLE
    inputs, jobs, plan = setup(full, bundle)
    save_json(work / "plan.json", plan)
    out = work / "rows"
    out.mkdir()

    def lane(i):
        for number in range(i, len(jobs), len(CPUS)):
            if perf_counter() - started >= seconds - CAP:
                break
            (query, paths), policy = jobs[number]
            row = attempt(query, paths, policy, inputs[query["recording"]], CPUS[i], bundle)
            save_json(out / f"{number:03}.json", row)
            print(
                row["id"],
                policy,
                row["result"]["status"],
                round(row["worker_wall_s"], 2),
                flush=True,
            )

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, range(len(CPUS))))
    save_json(work / "run-receipt.json", dict(elapsed_s=perf_counter() - started, cap_s=seconds))


def seal(work, output):
    plan = json.loads((work / "plan.json").read_bytes())
    rows = [json.loads(p.read_bytes()) for p in sorted((work / "rows").glob("*.json"))]
    envelope = gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0)
    write(output / "predictions.jsonl.gz", envelope)
    for name in ("plan.json", "run-receipt.json"):
        if (work / name).exists():
            write(output / name, (work / name).read_bytes())
    save_json(
        output / "prediction-lock.json",
        dict(
            attempted=len(rows),
            scheduled=len(plan["scheduled"]),
            predictions_sha256=digest(envelope),
            plan_sha256=digest((work / "plan.json").read_bytes()),
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--full", action="store_true")
    p.add_argument("--seconds", type=int, default=480)
    p.add_argument("--seal", action="store_true")
    args = p.parse_args()
    if not args.seal:
        run(local_output(args.work), args.full, args.seconds)
    seal(args.work, REPORT)


if __name__ == "__main__":
    main()
