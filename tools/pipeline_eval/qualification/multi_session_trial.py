"""Freeze and replay independent session likelihoods from authenticated GLRT."""

import argparse
import gzip
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

from .. import corpus, whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, local_output, save_json, write
from . import cold_input, sequential_fix_trial
from .full_v5_check import _sha

OUT = sequential_fix_trial.SCREEN / "retry-and-transfer/multi-session"
MODULE = "tools.pipeline_eval.qualification.multi_session_trial"
CPUS = (20, 21)
CAP_S = 150
MEMORY = 512 * 1024**2
NANO = 10**9
SPACING_NS = 12 * 3600 * NANO
PROFILES = "session-profiles.jsonl.gz"
PLAN = "blind-plan.json"
LOCK = "prediction-lock.json"


def selection():
    inventory = sequential_fix_trial.inventory()
    rooftop, audit = [], {}
    panels = dict(early="DS26", late="DS29")
    for group, panel in panels.items():
        eligible = sorted(
            (row["cutoff_utc_ns"], ident, row)
            for ident, row in inventory.items()
            if row["panel"] == panel
            and ident.startswith(panel + "-")
            and all(row.get(k) for k in ("native", "catalog", "recording", "request", "regions"))
        )
        audit[group] = []
        previous = -SPACING_NS
        for timestamp, ident, row in eligible:
            if timestamp - previous < SPACING_NS:
                continue
            item = dict(id=ident, cutoff_utc_ns=timestamp)
            audit[group].append(item)
            try:
                cap = cold_input.load(ident)
                if not 295 <= cap.duration_s <= 305:
                    raise ValueError("expected a complete five-minute capture")
            except (KeyError, OSError, ValueError) as error:
                item["ineligible"] = str(error)
                continue
            rooftop.append(
                dict(
                    item,
                    group=group,
                    tile=row["regions"][0],
                    native_sha256=cap.native_sha256,
                    catalog_sha256=cap.catalog_sha256,
                    capture_s=cap.duration_s,
                    catalog_timestamp_ns=cap.catalog_timestamp_ns,
                    request_sha256=row["request"]["sha256"],
                )
            )
            previous = timestamp
            if sum(r["group"] == group for r in rooftop) == 3:
                break
        if sum(r["group"] == group for r in rooftop) != 3:
            raise ValueError(f"expected three authenticated {panel} captures")
    if len({tuple(row["tile"]["center"]) for row in rooftop}) != 1:
        raise ValueError("roof captures do not share the same public offered tile")
    if len({row["native_sha256"] for row in rooftop}) != len(rooftop):
        raise ValueError("duplicate GLRT recording in the stationary panel")
    return rooftop, audit


def stage(work, report):
    if (report / PLAN).exists():
        raise FileExistsError("the stationary roster already exists")
    rows, audit = selection()
    work.mkdir(parents=True, mode=0o700)
    sources = (
        Path(__file__),
        Path(cold_input.__file__),
        ROOT / "tools/pipeline_eval/reference/grid.py",
        ROOT / "tools/pipeline_eval/variants/trackless_likelihood.py",
        ROOT / "tools/pipeline_eval/variants/multi_session.py",
        ROOT / "tools/pipeline_eval/variants/folded_doppler.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        corpus.FROZEN / "provenance.json",
        report / "PROTOCOL.md",
    )
    save_json(
        report / PLAN,
        dict(
            candidates=rows,
            eligibility=audit,
            cpus=list(CPUS),
            cap_s=CAP_S,
            address_space_bytes=MEMORY,
            sources={str(p.resolve()): _sha(p) for p in sources},
        ),
    )
    write(work / "plan.sha256", _sha(report / PLAN).encode())
    print([(row["id"], row["group"]) for row in rows], flush=True)


def worker():
    start, cpu = perf_counter(), process_time()
    setrlimit(RLIMIT_AS, (MEMORY, MEMORY))
    from ..variants import multi_session

    job = json.load(sys.stdin)
    if set(job) != {"capture", "center", "cpu"} or os.sched_getaffinity(0) != {job["cpu"]}:
        raise ValueError("stationary numerical worker has the wrong input or affinity")
    doc = job["capture"]
    if doc["catalog_timestamp_ns"] > doc["cutoff_utc_ns"]:
        raise ValueError("future orbit snapshot")
    capture = SimpleNamespace(**(doc | {"catalog": doc["catalog"].encode("ascii")}))
    profile = multi_session.profiles(capture, job["center"])
    print(
        json.dumps(
            dict(
                status="ok",
                profile=profile,
                cpu_s=process_time() - cpu,
                worker_wall_s=perf_counter() - start,
                peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            ),
            allow_nan=False,
        )
    )


def attempt(work, case, cpu):
    start = perf_counter()
    cap = cold_input.load(case["id"])
    if any(
        getattr(cap, name) != case[name]
        for name in ("native_sha256", "catalog_sha256", "cutoff_utc_ns", "catalog_timestamp_ns")
    ):
        raise ValueError("native GLRT or causal catalogue changed after locking")
    job = dict(
        capture=vars(cap) | {"catalog": cap.catalog.decode("ascii")},
        center=case["tile"]["center"],
        cpu=cpu,
    )
    payload = encoded(job)
    try:
        proc = subprocess.run(
            ["taskset", "-c", str(cpu), sys.executable, "-B", "-m", MODULE, "worker"],
            env=os.environ | THREAD_ENV,
            input=payload,
            capture_output=True,
            check=True,
            timeout=CAP_S,
        )
        result = json.loads(proc.stdout)
        if result["peak_rss_kib"] * 1024 > MEMORY:
            raise ValueError("numerical worker exceeded the address-space bound")
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        detail = (getattr(error, "stderr", None) or b"").decode(errors="replace")[-3000:]
        status = "timed_out" if isinstance(error, subprocess.TimeoutExpired) else "failed"
        result = dict(status=status, reason=detail or str(error))
    row = dict(
        case,
        cpu=cpu,
        input_sha256=sha256(payload).hexdigest(),
        direct_wall_s=perf_counter() - start,
        **result,
    )
    save_json(work / f"{case['id']}.json", row)
    print(
        row["id"], row["status"], round(row["direct_wall_s"], 2), row.get("reason", ""), flush=True
    )
    return row


def run(work, report):
    if (report / LOCK).exists():
        raise FileExistsError("the stationary predictions are already sealed")
    plan = whole_iq.read(whole_iq.checked(report / PLAN, (work / "plan.sha256").read_text()))
    for name, digest in plan["sources"].items():
        whole_iq.checked(Path(name), digest)
    ordered = [plan["candidates"][index :: len(CPUS)] for index in range(len(CPUS))]

    def lane(args):
        cases, cpu = args
        return [attempt(work, case, cpu) for case in cases]

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        rows = {
            row["id"]: row
            for group in pool.map(lane, zip(ordered, CPUS, strict=True))
            for row in group
        }
    for name, digest in plan["sources"].items():
        whole_iq.checked(Path(name), digest)
    ids = [row["id"] for row in plan["candidates"]]
    blob = gzip.compress(b"".join(encoded(rows[ident]) + b"\n" for ident in ids), mtime=0)
    write(report / PROFILES, blob)
    save_json(report / LOCK, dict(cases=ids, files={n: _sha(report / n) for n in (PLAN, PROFILES)}))


def main():
    if sys.argv[1:] == ["worker"]:
        return worker()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "run"))
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=OUT)
    args = parser.parse_args()
    return (stage if args.action == "stage" else run)(args.work, args.report)


if __name__ == "__main__":
    main()
