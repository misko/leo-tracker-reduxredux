"""Match eager and lazy compact v5 workers with independently sealed input bindings."""

import argparse
import gzip
import json
import os
import signal
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

from ..__main__ import (
    DEFAULT_OUT,
    ROOT,
    THREAD_ENV,
    encoded,
    public_cases,
    references,
    save_json,
    write,
)
from ..scoring import ARMS, distance_km, validate_result
from ..variants import compact_finish, v5_lazy_pair, v5_lean

OUTPUT = ROOT / "reports/2026_11_19_receiver_screening/lazy-pair"
CONTROL = "compact_finish_eager"
CANDIDATE = v5_lazy_pair.METHOD
SOURCES = (
    "compact_finish.py",
    "orbit_projector.py",
    "orbit_projector.c",
    "v5_core.py",
    "v5_lean.py",
    "v5_lazy_pair.py",
)
PRIMARY = {"DS26-0036", "DS29-0082"}


def digest(raw):
    return sha256(raw).hexdigest()


def source_receipt():
    frozen = v5_lean.SOURCE / "leo/analysis/localization_v3"
    variant_root = Path(v5_lazy_pair.__file__).parent
    return dict(
        frozen_source_sha256=v5_lean.SOURCE_SHA256,
        frozen_files={
            name: digest((frozen / name).read_bytes())
            for name in (
                "history_policy.py",
                "signed_context.py",
                "predictive_linear.py",
                "position.py",
            )
        },
        local_files={name: digest((variant_root / name).read_bytes()) for name in SOURCES},
        harness_sha256=digest(Path(__file__).read_bytes()),
    )


def _public(case_id):
    panel = "ds26-common127" if case_id.startswith("DS26-") else "roof16"
    source, refs = references(panel, [case_id])
    return public_cases(source, refs, DEFAULT_OUT / "inputs")[0]


def _measure(case, cpu, method, work):
    request, target, log, clock = (
        work / name for name in ("input.json", "output.json", "run.log", "time")
    )
    save_json(request, case)
    command = [
        "/usr/bin/time",
        "-f",
        "%U %S",
        "-o",
        str(clock),
        "taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.lazy_pair_trial",
        "worker",
        method,
        str(request),
        str(target),
        str(work),
    ]
    start = perf_counter()
    with log.open("wb") as stream:
        process = subprocess.Popen(
            command,
            stdout=stream,
            stderr=stream,
            cwd=ROOT,
            env={**os.environ, **THREAD_ENV},
            start_new_session=True,
        )
        timed_out = False
        try:
            process.wait(timeout=300)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
    wall = perf_counter() - start
    if process.returncode or not target.is_file():
        message = log.read_text(errors="replace")[-1600:]
        result = dict(
            status="timed_out" if timed_out else "failed",
            reason=message or "worker failed",
            metrics={},
            boundary=compact_finish.BOUNDARY,
            arms={arm: {"latlon": None} for arm in ARMS},
        )
    else:
        result = json.loads(target.read_bytes())
    validate_result(result)
    user, system = (
        map(float, clock.read_text().split())
        if clock.is_file() and clock.stat().st_size and not process.returncode
        else (None, None)
    )
    return dict(
        id=case["id"],
        method=method,
        cpu=cpu,
        input_sha256=digest(encoded(case)),
        worker_wall_s=wall,
        worker_cpu_s=user + system if user is not None else None,
        worker_user_s=user,
        worker_system_s=system,
        result=result,
    )


def run_case(output, case_id, cpu, first):
    case = _public(case_id)
    request = Path(case["request_path"]).read_bytes()
    order = (CONTROL, CANDIDATE) if first == "eager" else (CANDIDATE, CONTROL)
    target = output / "cases" / case_id
    if (target / "seal.json").exists():
        raise FileExistsError("this paired case is already sealed")
    plan = dict(
        id=case_id,
        cpu=cpu,
        order=list(order),
        input_sha256=digest(encoded(case)),
        native_sha256=case["native_sha256"],
        frozen_request_sha256=digest(request),
        protocol_sha256=digest((output / "PROTOCOL.md").read_bytes()),
        sources=source_receipt(),
    )
    save_json(target / "plan.json", plan)
    result_hashes = {}
    for method in order:
        with TemporaryDirectory(prefix=f"v5-lazy-pair-{case_id}-") as directory:
            row = _measure(case, cpu, method, Path(directory))
        name = f"{method}.json"
        save_json(target / name, row)
        result_hashes[name] = digest((target / name).read_bytes())
        print(
            case_id,
            method,
            row["result"]["status"],
            round(row["worker_wall_s"], 2),
            row["worker_cpu_s"],
            list(row["result"]["metrics"].get("predictive_pair", ())),
            flush=True,
        )
    if plan["sources"] != source_receipt():
        raise ValueError("source changed during the paired replay")
    result_hashes["plan.json"] = digest((target / "plan.json").read_bytes())
    save_json(target / "seal.json", result_hashes)


def compare(control, candidate):
    if (control["id"], control["cpu"], control["input_sha256"]) != (
        candidate["id"],
        candidate["cpu"],
        candidate["input_sha256"],
    ):
        raise ValueError("replays used different inputs or CPU boundaries")
    reference, modified = (row["result"] for row in (control, candidate))
    verified = reference["status"] == modified["status"] == "ok"
    report = dict(
        id=control["id"],
        statuses=[r["status"] for r in (reference, modified)],
        positions_exact=False,
        metrics_exact=False,
        predicate_exact=False,
        case_wall_s=[r["worker_wall_s"] for r in (control, candidate)],
        case_cpu_s=[r["worker_cpu_s"] for r in (control, candidate)],
    )
    if not verified:
        return report

    def scientific(value):
        return {
            k: v
            for k, v in value["metrics"].items()
            if k not in {"predictive_pair", "stage_s", "candidate_s"}
        }

    (a,), (b,) = (r["metrics"]["predictive_pair"] for r in (reference, modified))

    def comparison(item):
        return {k: v for k, v in item.items() if k not in {"calls", "fitted_diagnostic"}}

    calls = [[len(item["calls"][arm]) for arm in ARMS] for item in (a, b)]
    conditional = {}
    for arm in ARMS:
        eager, lazy = [
            dict(
                result["arms"][arm],
                conditional_rms_hz=result["metrics"].get(f"{arm}_conditional_rms_hz"),
                frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
            )
            for result in (reference, modified)
        ]
        conditional[arm] = dict(
            control=eager, lazy=lazy, delta_km=distance_km(eager["latlon"], lazy["latlon"])
        )
    report.update(
        positions_exact=encoded(reference["arms"]) == encoded(modified["arms"]),
        metrics_exact=encoded(scientific(reference)) == encoded(scientific(modified)),
        predicate_exact=encoded(comparison(a)) == encoded(comparison(b)),
        c0_passed=a["c0_passed"],
        pair_accepted=a["pair_accepted"],
        calls=calls,
        expected_calls=([[1, 1], [1, int(a["c0_passed"])]] == calls),
        conditional=conditional,
        decisive_policy=[a, b],
        saved_eager_fitted_s=a["calls"]["fitted_c"][0] if not a["c0_passed"] else None,
    )
    return report


def score(output, ids):
    if len(ids) != len(set(ids)) or not set(ids) >= PRIMARY:
        raise ValueError("need both primary cases and no duplicates")
    rows, reference, candidate, seals = [], [], [], {}
    for case in ids:
        folder = output / "cases" / case
        lock = json.loads((folder / "seal.json").read_bytes())
        for name, expected in lock.items():
            if digest((folder / name).read_bytes()) != expected:
                raise ValueError(f"{case} receipt or plan changed")
        seals[case] = digest((folder / "seal.json").read_bytes())
        a, b = (
            json.loads((folder / f"{method}.json").read_bytes()) for method in (CONTROL, CANDIDATE)
        )
        rows.append(compare(a, b))
        reference.append(a)
        candidate.append(b)
    archives = dict(cases=seals)
    for name, records in (
        ("positions.jsonl.gz", candidate),
        ("control-positions.jsonl.gz", reference),
    ):
        payload = gzip.compress(b"".join(encoded(r) + b"\n" for r in records), mtime=0)
        write(output / name, payload)
        archives[name] = digest(payload)
    save_json(output / "comparison.json", rows)
    archives["comparison.json"] = digest((output / "comparison.json").read_bytes())
    save_json(output / "prediction-lock.json", archives)
    return all(
        all(
            row.get(key)
            for key in ("positions_exact", "metrics_exact", "predicate_exact", "expected_calls")
        )
        for row in rows
    )


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        method, request, target, work = sys.argv[2:]
        case = json.loads(Path(request).read_bytes())
        save_json(Path(target), v5_lazy_pair.run(case, Path(work), eager=method == CONTROL))
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT)
    parser.add_argument("--cpu", type=int)
    parser.add_argument("--first", choices=("eager", "lazy"), default="eager")
    parser.add_argument("--score", action="store_true")
    parser.add_argument("case", nargs="+")
    args = parser.parse_args()
    if args.score:
        return 0 if score(args.out, args.case) else 1
    if args.cpu is None or len(args.case) != 1:
        parser.error("prediction requires an explicit CPU and one case")
    run_case(args.out, args.case[0], args.cpu, args.first)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
