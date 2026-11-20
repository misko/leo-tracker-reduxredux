"""Run the roof-parity original v5 worker on sealed hybrid waveform offers."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import monotonic
from uuid import uuid4

from ..__main__ import ROOT, THREAD_ENV, local_output, save_json, write
from ..scoring import validate_result
from . import v5_regional_blind as blind
from . import v5_regional_reference as original
from .phase_support_results import pack

REPORT = ROOT / "reports/2026_11_19_receiver_screening/support-preserving/hybrid-v5"
CPUS = (20, 21)
COHORTS = ("hybrid", "donor-only")
VISIT_LIMIT = 240
METHOD = "hybrid_original_v5"


def read_rows(path, cutoff=None):
    rows = original.read(path)
    if not isinstance(rows, list) or len(rows) != 2:
        raise ValueError("each predeclared acquisition arm requires exactly two opaque offers")
    if cutoff is not None:
        if any(row.get("cutoff_utc_ns", cutoff) != cutoff for row in rows):
            raise ValueError("declared cutoff differs from authenticated native clock")
        rows = [dict(row, cutoff_utc_ns=cutoff) for row in rows]
    return blind.select_pair(rows)


def check_seal(path, expected, manifest):
    original.checked(path, expected)
    lock = original.read(path)
    sha = original.sha(manifest)
    # The producer can seal a copied manifest under either schema without a path dependency.
    if sha not in (
        lock.get("requests_sha256"),
        lock.get("request_sha256"),
        lock.get("files", {}).get("requests.json"),
    ):
        raise ValueError("the detector seal does not bind the consumed public requests")
    return sha


def resolve_public(public, declared):
    """Only the native arm file and two known shared physical inputs are admitted."""
    parent = public.parent
    fields = dict(
        native=public / "native.json",
        track_config=parent / "track-config.json",
        archive=parent / "tle",
    )
    rooted = {}
    for name, path in fields.items():
        filename = Path(declared[name])
        if filename.name != str(filename) or (public / filename).resolve() != path:
            raise ValueError("controller input resolves outside the arm/shared public layout")
        rooted[name] = str(path.relative_to(parent))
    return rooted


def prospective(report):
    path = report / "source-lock.json"
    parity = original.REPORT / "roof-retry/parity.json"
    if not original.read(parity)["exact"]:
        raise ValueError("original numerical reference requires exact measured roof parity")
    sources = (
        Path(__file__),
        Path(original.__file__),
        Path(blind.__file__),
        Path(original.v5_lean.__file__),
        report / "PROTOCOL.md",
        parity,
    )
    lock = dict(
        files={str(p): original.sha(p) for p in sources},
        cohorts=COHORTS,
        cpus=CPUS,
        methods=[METHOD],
        limit_s=VISIT_LIMIT,
        memory_max=original.MEMORY,
        swap_max=0,
        arms=original.v5_lean.ARMS,
        frozen_source_sha256=original.v5_lean.SOURCE_SHA256,
        frozen_runner_sha256=original.v5_lean.RUNNER_SHA256,
    )
    if path.exists():
        if original.read(path) != json.loads(json.dumps(lock)):
            raise ValueError("prospective source or study protocol changed")
    else:
        save_json(path, lock)
    return original.sha(path)


def isolated(attempt, cpu, private_root):
    runtime = original.v5_lean
    return [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--die-with-parent",
        "--unshare-net",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--bind",
        str(attempt),
        str(attempt),
        "--tmpfs",
        str(private_root),
        str(runtime.PYTHON),
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.hybrid_v5",
        "worker",
        str(attempt),
        str(cpu),
    ]


def worker(attempt, cpu):
    if cpu not in CPUS:
        raise ValueError("original v5 started outside its assigned roster")
    # Select the predeclared CPU witness without changing original validation or numerical work.
    original.CPU = cpu
    original.worker(attempt / "request.json", attempt / "result.json")


def attempt(request, path, cpu, private_root):
    path.mkdir(parents=True, exist_ok=False)
    tmp = path / "tmp"
    tmp.mkdir()
    request["job"]["output_root"] = str(path)
    actual = path / "request.json"
    original.write(actual, request)
    unit = "leo-hybrid-v5-" + uuid4().hex[:12]
    runtime = original.v5_lean
    command = [
        "systemd-run",
        "--user",
        "--wait",
        f"--unit={unit}",
        f"--property=MemoryMax={original.MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={VISIT_LIMIT}s",
        "--property=TimeoutStopSec=4s",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--property=StandardOutput=append:{path / 'stages.log'}",
        "--property=StandardError=inherit",
        f"--working-directory={ROOT}",
        f"--setenv=TMPDIR={tmp}",
        f"--setenv=PYTHONPATH={runtime.SOURCE}:{runtime.RUNNER}:{ROOT}",
        *(f"--setenv={key}={value}" for key, value in THREAD_ENV.items()),
        *isolated(path, cpu, private_root),
    ]
    began = monotonic()
    log = path / "service.log"
    with log.open("xb") as stream:
        try:
            check = subprocess.run(command, stdout=stream, stderr=stream, timeout=VISIT_LIMIT + 15)
        except subprocess.TimeoutExpired:
            subprocess.run(["systemctl", "--user", "kill", "--signal=KILL", unit], check=False)
            check = None
    note = log.read_text(errors="replace")
    resources = {
        name: original.read(path / f"{name}.json")
        for name in ("start", "finish")
        if (path / f"{name}.json").exists()
    }
    if check is not None and check.returncode == 0 and "finish" in resources:
        result = original.read(path / "result.json")
        for arm, endpoint in result["arms"].items():
            rf = result["metrics"].get(f"{arm}_conditional_rms_hz")
            if rf is not None:
                endpoint["rf_rms_hz"] = rf
    else:
        state = "timed_out" if check is None or "result: timeout" in note else "failed"
        result = runtime._no_fix(state + " in original v5 numerical service", status=state)
    validate_result(result)
    finish = resources.get("finish", {})
    start = resources.get("start", {})
    return dict(
        result=result,
        method=METHOD,
        cpu=cpu,
        unit=unit,
        worker_wall_s=monotonic() - began,
        worker_cpu_s=finish["cpu_s"] - start["cpu_s"] if start and finish else None,
        worker_cgroup_peak_bytes=finish.get("memory_peak_bytes"),
        exit_code=check.returncode if check else None,
        resources=resources,
        request_sha256=original.sha(actual),
    )


def run(cohort, public, detector_lock, detector_sha, private, scratch, report):
    source_sha = prospective(report)
    if not public.is_relative_to(private) or scratch.is_relative_to(private):
        raise ValueError("private custodian directory must mask public origins, not staged inputs")
    requests = detector_lock.parent / "requests.json"
    request_sha = check_seal(detector_lock, detector_sha, requests)
    lock = original.read(detector_lock)
    if not lock["ready"] or lock["completed_visits"] != lock["scheduled_visits"]:
        raise ValueError("the sealed arm does not contain a complete physical schedule")
    source_rows = {r["id"]: r for r in original.read(requests)}
    paths = {ident: resolve_public(public, row) for ident, row in source_rows.items()}
    native = public / "native.json"
    for row in source_rows.values():
        original.checked(native, row["native_sha256"])
    cutoff = original.read(native)["clock_anchor"]["before"]["realtime_ns"]
    rows = read_rows(requests, cutoff)
    bound = [dict(row, **paths[row["id"]]) for row in rows]
    work = scratch / cohort
    work.mkdir(parents=True, exist_ok=False)
    study = report / cohort
    study.mkdir(exist_ok=False)
    jobs, history = blind.prepare(bound, public.parent, work)
    asset = detector_lock.parent / "causal-authority.json"
    original.checked(asset, lock["files"][asset.name])
    authority = {name: row["sha256"] for name, row in original.read(asset).items()}
    actual = {p.name: original.sha(p) for p in (public.parent / "tle").rglob("*.tle")}
    if history != actual or actual != authority:
        raise ValueError("original and compact must use the same causal archive")
    remapped = []
    for meta, job in jobs:
        offer = meta["id"]
        remapped.append(
            (
                dict(
                    meta,
                    offer_id=offer,
                    id=f"{cohort}-{offer}",
                    input_sha256=blind.digest_json(source_rows[offer]),
                ),
                job,
            )
        )
    jobs = remapped
    write(study / "requests.json", requests.read_bytes())
    save_json(study / "causal-snapshots.json", history)
    save_json(
        study / "input-lock.json",
        dict(
            request_sha256=request_sha,
            detector_lock_sha256=detector_sha,
            source_lock_sha256=source_sha,
            jobs=[dict(meta, cpu=cpu) for (meta, _), cpu in zip(jobs, CPUS, strict=True)],
            catalogue_history_sha256=blind.digest_json(history),
        ),
    )

    def solve(job, cpu):
        meta, request = job
        path = work / meta["id"]
        row = dict(meta, cohort=cohort, **attempt(request, path, cpu, private))
        for name in ("service.log", "stages.log"):
            member = path / name
            if member.is_file():
                write(study / f"{meta['id']}-{name}", member.read_bytes())
        print(
            cohort, meta["id"], row["result"]["status"], round(row["worker_wall_s"], 3), flush=True
        )
        return row

    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        fitted = list(pool.map(solve, jobs, CPUS))
    prospective(report)
    check_seal(detector_lock, detector_sha, requests)
    pack(study / "positions.jsonl.gz", fitted)
    files = {p.name: original.sha(p) for p in study.iterdir() if p.is_file()}
    save_json(study / "prediction-lock.json", dict(cases=[r["id"] for r in fitted], files=files))


def seal(report):
    source = prospective(report)
    rows, nested = [], {}
    from .whole_pressure_trial import rows_from

    for cohort in COHORTS:
        folder = report / cohort
        path = folder / "prediction-lock.json"
        lock = original.read(path)
        for name, digest in lock["files"].items():
            original.checked(folder / name, digest)
        actual = rows_from(folder / "positions.jsonl.gz")
        if lock["cases"] != [r["id"] for r in actual]:
            raise ValueError("incomplete original v5 roster")
        rows.extend(actual)
        nested[str(path.relative_to(report))] = original.sha(path)
    pack(report / "positions.jsonl.gz", rows)
    save_json(
        report / "prediction-lock.json",
        dict(
            cases=[r["id"] for r in rows],
            files={
                "source-lock.json": source,
                "positions.jsonl.gz": original.sha(report / "positions.jsonl.gz"),
                **nested,
            },
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for mode in ("freeze", "seal"):
        sub.add_parser(mode).add_argument("--out", type=local_output, default=REPORT)
    replay = sub.add_parser("run")
    replay.add_argument("cohort", choices=COHORTS)
    replay.add_argument("--public", type=Path, required=True)
    replay.add_argument("--private", type=Path, required=True)
    replay.add_argument("--detector-lock", type=Path, required=True)
    replay.add_argument("--detector-sha256", required=True)
    replay.add_argument("--scratch", type=local_output, required=True)
    replay.add_argument("--out", type=local_output, default=REPORT)
    child = sub.add_parser("worker")
    child.add_argument("path", type=local_output)
    child.add_argument("cpu", type=int)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.path, args.cpu)
    elif args.action == "run":
        run(
            args.cohort,
            args.public.resolve(),
            args.detector_lock,
            args.detector_sha256,
            args.private.resolve(),
            args.scratch,
            args.out,
        )
    else:
        {"freeze": prospective, "seal": seal}[args.action](args.out)


if __name__ == "__main__":
    main()
