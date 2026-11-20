"""Run the released compact position profiles on a fresh blind native GLRT panel."""

import argparse
import gzip
import json
import os
import secrets
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

import numpy as np

from .. import cavity_runtime, whole_iq
from ..__main__ import ROOT, THREAD_ENV, encoded, save_json, write
from ..scoring import ARMS, validate_result
from ..variants import v5_lean
from . import cold_scenes
from . import compact_blind_generator as generator
from . import portable_v5_transfer as existing
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/compact-blind"
CPUS = (14, 15)
CANDIDATE = "phase-release"
CONTROL = "compact"
METHODS = (CANDIDATE, CONTROL)
LIMIT_S = 175
BOUNDARY = "Simulated native wideband GLRT and causal TLEs to released compact position"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def source_lock(out):
    sources = (
        Path(__file__),
        Path(generator.__file__),
        Path(cold_scenes.__file__),
        Path(existing.__file__),
        Path(cavity_runtime.__file__),
        Path(cavity_runtime.__file__).with_name("cavity_entry.py"),
        out / "PROTOCOL.md",
        v5_lean.SOURCE / "leo/operations/localization_v3_job.py",
    )
    return dict(
        sources={str(p): digest(p) for p in sources},
        cpus=list(CPUS),
        limit_s=LIMIT_S,
        profiles={
            method: {
                name: sha256(data).hexdigest()
                for name, data in cavity_runtime.release_files(
                    cavity_runtime.RELEASE, method
                ).items()
            }
            for method in METHODS
        },
    )


def verify_geometry_guard(case, public, work):
    _, archived = whole_iq.binding("DS26-0036")
    job = dict(
        archived["job"],
        native_input=dict(
            path=str(public / case["native"]), sha256="sha256:" + case["native_sha256"]
        ),
        track_config=dict(
            path=str(public / case["track_config"]), sha256="sha256:" + case["config_sha256"]
        ),
        identity=dict(
            run_id="experiment-" + case["id"],
            session_id=case["session"],
            input_sha256="sha256:" + case["native_sha256"],
        ),
        title=case["id"],
        scan_identities=[case["session"]],
        tle_root=str(public / case["archive"]),
        output_root=str(work / "original-preflight"),
        search_center=case["tile"],
        screen_center=case["screen_center"],
    )
    script = """
import json, sys
from leo.operations.localization_v3_job import validate_request
request = json.load(sys.stdin)
try:
    validate_request(request)
except ValueError as error:
    print(str(error))
else:
    print('accepted')
"""
    result = subprocess.run(
        [str(v5_lean.PYTHON), "-B", "-c", script],
        input=encoded(job),
        capture_output=True,
        env=dict(os.environ, PYTHONPATH=str(v5_lean.SOURCE), PYTHONSAFEPATH="1"),
        check=True,
        timeout=20,
    )
    reason = result.stdout.decode().strip()
    if reason != "Current published figure contract requires the production regional frame":
        raise ValueError("unexpected validation outcome for the unmodified original v5 job")
    return dict(
        status="unavailable",
        stage="unchanged original v5 job validator",
        reason=reason,
        input_sha256=sha256(encoded(job)).hexdigest(),
        truth_present=False,
        request=job,
    )


def prepare(work, out, seed_hex=None):
    if (out / "source-lock.json").exists():
        raise ValueError("choose a new report directory for a new prospectively locked replay")
    work.mkdir(mode=0o700)
    public = work / "public"
    public.mkdir(mode=0o700)
    seal = source_lock(out)
    save_json(out / "source-lock.json", seal)
    seed = bytes.fromhex(seed_hex) if seed_hex else secrets.token_bytes(32)
    if len(seed) != 32:
        raise ValueError("expected a 32-byte fixed seed")
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    collected, nominal, history, objects = existing.authentic_history()
    leaves = public / "tle/archive/space-track"
    leaves.mkdir(parents=True)
    receipt = {}
    for ref in sorted(history, key=lambda r: (r["collected_utc_ns"], r["sha256"])):
        filename = f"{ref['collected_utc_ns']}-{ref['sha256']}.tle"
        raw = objects[ref["sha256"]].read_bytes()
        if sha256(raw).hexdigest() != ref["sha256"]:
            raise ValueError("an archived causal TLE object changed while staging")
        write(leaves / filename, raw)
        receipt[filename] = ref
    _, frozen = whole_iq.binding("DS26-0036")
    config = public / "track-config.json"
    write(config, Path(frozen["job"]["track_config"]["path"]).read_bytes())
    jobs, truth = [], {}
    (public / "native").mkdir()
    (out / "native").mkdir()
    for i in range(len(generator.BOXES)):
        anchor, probes, counter, offers, physical = generator.make_case(nominal, collected, i, rng)
        session = rng.bytes(16).hex()
        document = existing.simulated_document(session, anchor, probes, counter)
        filename = f"native/{session}.json"
        write(public / filename, encoded(document) + b"\n")
        write(out / (filename + ".gz"), gzip.compress((public / filename).read_bytes(), mtime=0))
        input_hash = digest(public / filename)
        cutoff = document["clock_anchor"]["before"]["realtime_ns"]
        if any(r["collected_utc_ns"] > cutoff for r in receipt.values()):
            raise ValueError("post-cutoff collection entered a synthetic native input")
        for condition, tile in offers.items():
            opaque = rng.bytes(16).hex()
            jobs.append(
                dict(
                    id=opaque,
                    session=session,
                    native=filename,
                    native_sha256=input_hash,
                    track_config=config.name,
                    config_sha256=digest(config),
                    archive="tle",
                    catalog_sha256=sha256(nominal).hexdigest(),
                    cutoff_utc_ns=cutoff,
                    tile=tile,
                    screen_center=tile,
                )
            )
            truth[opaque] = dict(condition=condition, session=session, **physical)
    public_plan = public / "requests.json"
    rng.shuffle(jobs)
    save_json(public_plan, jobs)
    save_json(work / "custodian-only.json", dict(seed_hex=seed.hex(), targets=truth))
    save_json(out / "requests.json", jobs)
    write(out / config.name, config.read_bytes())
    save_json(out / "catalogue-authority.json", receipt)
    save_json(out / "unchanged-v5-preflight.json", verify_geometry_guard(jobs[0], public, work))
    save_json(
        out / "input-lock.json",
        dict(
            source_sha256=digest(out / "source-lock.json"),
            request_sha256=digest(public_plan),
            catalogue_authority_sha256=digest(out / "catalogue-authority.json"),
            private_sha256=digest(work / "custodian-only.json"),
            seed_sha256=sha256(seed).hexdigest(),
        ),
    )
    print(public.resolve(), flush=True)


def isolated(work, public, install, case, cpu):
    exe, base, prefix = Path(sys.executable), Path(sys.base_prefix), Path(sys.prefix)
    command = [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--dev",
        "/dev",
        "--proc",
        "/proc",
        "--tmpfs",
        "/tmp",
        "--chdir",
        "/tmp",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PATH",
        "/usr/bin",
    ]
    for key, value in THREAD_ENV.items():
        command.extend(("--setenv", key, value))
    aliases = [str((exe.parent / exe.readlink()).parent.parent)] if exe.is_symlink() else []
    mounts = [(p, p) for p in ("/usr", "/lib", "/lib64", str(base), str(prefix), str(install))]
    mounts.extend((str(base), alias) for alias in aliases if alias != str(base))
    mounts.extend(
        (str(public / name), f"/public/{name}")
        for name in (
            case["native"],
            case["track_config"],
            case["archive"],
        )
    )
    for origin, target in mounts:
        command.extend(("--ro-bind", origin, target))
    return [
        "/usr/bin/time",
        "-f",
        "%U %S %M",
        "-o",
        str(work / "resource.txt"),
        *command,
        str(exe),
        "-IB",
        str(install),
        "--native",
        f"/public/{case['native']}",
        "--native-sha256",
        case["native_sha256"],
        "--track-config",
        f"/public/{case['track_config']}",
        "--config-sha256",
        case["config_sha256"],
        "--session",
        case["session"],
        "--archive",
        f"/public/{case['archive']}",
        "--tile",
        *map(str, case["tile"]),
        "--screen-center",
        *map(str, case["screen_center"]),
    ]


def attempt(public, install, case, work, cpu, method):
    work.mkdir(parents=True, exist_ok=False)
    began = perf_counter()
    with (work / "stderr.log").open("wb") as log:
        process = subprocess.Popen(
            isolated(work, public, install, case, cpu),
            stdout=subprocess.PIPE,
            stderr=log,
            start_new_session=True,
        )
        try:
            body, _ = process.communicate(timeout=LIMIT_S)
            if process.returncode:
                lines = (work / "stderr.log").read_text(errors="replace").strip().splitlines()
                reason, status = lines[-1] if lines else f"exit {process.returncode}", "failed"
            else:
                reason, status = None, None
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            reason, status = f"Reached {LIMIT_S} s wall deadline", "timed_out"
    elapsed = perf_counter() - began
    result = (
        json.loads(body)
        if status is None
        else dict(
            status=status,
            reason=reason,
            boundary=BOUNDARY,
            metrics={},
            arms={a: dict(latlon=None) for a in ARMS},
        )
    )
    validate_result(result)
    resource = work / "resource.txt"
    user, system, rss = (
        resource.read_text().splitlines()[-1].split()
        if resource.is_file() and (resource.stat().st_size > 0)
        else (None, None, None)
    )
    row = dict(
        id=case["id"],
        method=method,
        result=result,
        cpu=cpu,
        worker_wall_s=elapsed,
        worker_cpu_s=float(user) + float(system) if user is not None else None,
        peak_rss_kib=int(rss) if rss is not None else None,
        input_sha256=sha256(encoded(case)).hexdigest(),
        native_sha256=case["native_sha256"],
        catalogue_sha256=case["catalog_sha256"],
    )
    save_json(work / "result.json", row)
    print(case["id"], method, result["status"], round(elapsed, 2), flush=True)
    return row


def predict(work, out):
    pin = read(out / "input-lock.json")
    public = work / "public"
    if pin["request_sha256"] != digest(public / "requests.json") or (
        pin["source_sha256"] != digest(out / "source-lock.json")
        or source_lock(out) != read(out / "source-lock.json")
    ):
        raise ValueError("the receiver source or blind requests differ from their frozen bytes")
    if (out / "prediction-lock.json").exists():
        raise ValueError("this prediction panel is already sealed")
    history = out / "catalogue-authority.json"
    if digest(history) != pin["catalogue_authority_sha256"] or any(
        digest(public / "tle/archive/space-track" / f) != r["sha256"]
        for f, r in read(history).items()
    ):
        raise ValueError("staged TLE archive differs from its causal collections")
    jobs = read(public / "requests.json")
    if len(jobs) != 8 or any(
        digest(public / j["native"]) != j["native_sha256"]
        or digest(public / j["track_config"]) != j["config_sha256"]
        for j in jobs
    ):
        raise ValueError("staged public native factors differ from their immutable plan")
    installed = {m: cavity_runtime.install(work / m, profile=m) for m in METHODS}
    receipts = {m: whole_iq.receiver_identity(directory) for m, directory in installed.items()}
    save_json(out / "executables.json", receipts)

    def run_lane(lane, cpu):
        results = []
        for i in range(lane, len(jobs), len(CPUS)):
            case = jobs[i]
            for m in METHODS if (i // len(CPUS) + lane) % 2 == 0 else reversed(METHODS):
                folder = work / "attempts" / case["id"] / m
                results.append(attempt(public, installed[m], case, folder, cpu, m))
        return results

    start = perf_counter()
    with ThreadPoolExecutor(max_workers=len(CPUS)) as pool:
        tasks = [pool.submit(run_lane, i, cpu) for i, cpu in enumerate(CPUS)]
        rows = [r for task in tasks for r in task.result()]
    pack(out, "positions.jsonl.gz", sorted(rows, key=lambda r: (r["id"], r["method"])))
    files = (
        "positions.jsonl.gz",
        "source-lock.json",
        "input-lock.json",
        "requests.json",
        "catalogue-authority.json",
        "executables.json",
        "unchanged-v5-preflight.json",
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            files={f: digest(out / f) for f in files},
            worker_wall_s=perf_counter() - start,
            expected=[j["id"] for j in jobs],
            methods=list(METHODS),
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "predict"))
    parser.add_argument("work", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--seed-hex")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.work.resolve(), args.out.resolve(), args.seed_hex)
    else:
        predict(args.work.resolve(), args.out.resolve())


if __name__ == "__main__":
    main()
