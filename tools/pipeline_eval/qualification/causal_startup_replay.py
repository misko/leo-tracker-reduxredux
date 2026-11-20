"""Measure shifted input release with unchanged ordinary compact-cavity fitting."""

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import monotonic, monotonic_ns, process_time, sleep

from ..__main__ import encoded, local_output, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import orbit_projector, v5_causal_startup, v5_direct_cavity, v5_lean
from . import direct_cavity_trial as direct
from . import whole_cavity, whole_pair
from .full_receiver_comparison import ROOT, read, require_fields, seal, sha

REPORT = direct.REPORT.parent.parent / "next/causal-startup"
CASES = {
    "DS26-0036": (20, ("stock", "early"), whole_cavity.RUNS),
    "DS29-0082": (21, ("early", "stock"), whole_pair.RUNS),
}
LIMIT, LEAD, NICE = 155, 20, 10
MATCH = ("input_sha256", "native_sha256", "catalog_sha256", "tile")


def load_plan(work):
    return read(work / "plan.json")


def current_rss():
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1])
    raise ValueError("Linux process RSS is unavailable")


def sources():
    local = (Path(__file__), Path(v5_causal_startup.__file__), REPORT / "PROTOCOL.md")
    stock = seal(direct.REPORT, "receipt.json", ("positions.jsonl.gz", "bundle.json"))
    bundle = read(direct.REPORT / "bundle.json")
    entry = str(Path(v5_direct_cavity.__file__).relative_to(ROOT))
    source = dict(
        files={p.name: sha(p) for p in local},
        direct_receiver_sha256=sha(Path(v5_direct_cavity.__file__)),
        direct_prediction_lock_sha256=sha(direct.REPORT / "receipt.json"),
        whole_pair_prediction_lock_sha256=sha(whole_pair.REPORT / "prediction-lock.json"),
    )
    if source["direct_receiver_sha256"] != bundle["files"][entry]:
        raise ValueError("the active direct cavity worker differs from the sealed reference")
    require_fields(stock, dict(source_lock_sha256=sha(direct.REPORT / "source-lock.json")))
    return source, bundle


def verify_input(ident):
    case, request, binding = direct.input_case("ordinary-" + ident)
    return case, request, {key: binding[key] for key in MATCH}


def lock(work):
    work.mkdir(parents=True, exist_ok=False)
    authority, bundle = sources()
    orbit_projector.compile_kernel(work / "orbit_projector.so")
    archives = read_predictions(direct.REPORT / "positions.jsonl.gz")
    baseline = seal(
        whole_pair.REPORT, "prediction-lock.json", ("positions.jsonl.gz", "stages.json.gz")
    )
    require_fields(baseline, dict(source_lock_sha256=sha(whole_pair.REPORT / "source-lock.json")))
    whole = read(whole_pair.REPORT / "source-lock.json")["inputs"]
    rows, first = {}, {}
    for ident, (cpu, order, directory) in CASES.items():
        case, request, binding = verify_input(ident)
        if any(
            bundle["files"][name] != sha(v5_lean.SOURCE / name)
            for name in request["source"]["files"]
        ):
            raise ValueError("the frozen numerical runtime differs from the staged direct source")
        require_fields(archives[ident], binding)
        require_fields(whole[ident], dict(native_sha256=binding["native_sha256"]))
        job = request["job"]
        if (
            job["evaluation_reference"] is not None
            or request["native_manifest"]["binary_sha256"] != bundle["binary"]
        ):
            raise ValueError("unmatched numerical bound or evaluation reference")
        with (directory / ident / "replayed-0.jsonl").open() as stream:
            opening = json.loads(stream.readline())
        if opening["visit"] != 0 or opening["clock_anchor"]["after"] != opening["delivery_clock"]:
            raise ValueError("missing or invalid first-visit timing bracket")
        first[ident] = dict(
            anchor=opening["clock_anchor"],
            visit=0,
            first_iq_sha256=opening["iq_sha256"],
            lane_sha256=sha(directory / ident / "replayed-0.jsonl"),
        )
        rows[ident] = dict(binding, cpu=cpu, order=order, session=case["session_id"])
        # The early process gets no path to native data, no final timing, and no probe rows.
        save_json(
            work / f"{ident}-early.json",
            dict(
                ident=ident,
                session=case["session_id"],
                anchor=first[ident]["anchor"],
                track_config=job["track_config"],
                native_manifest=request["native_manifest"],
                native_sha256=binding["native_sha256"],
                archive=job["tle_root"],
                screen_center=job["screen_center"],
                tile=job["search_center"],
            ),
        )
    save_json(
        work / "plan.json",
        dict(
            cases=list(CASES),
            rows=rows,
            first_visit=first,
            sources=authority,
            lead_s=LEAD,
            per_worker_limit_s=LIMIT,
            library_sha256=sha(work / "orbit_projector.so"),
            early_packet_sha256={i: sha(work / f"{i}-early.json") for i in CASES},
        ),
    )


def numerical(work, ident, mode, out):
    from leo.analysis.localization_v3.region import SearchRegion
    from leo.analysis.localization_v4.backend import validate_manifest
    from leo.analysis.localization_v4.native_bound import NativeBound

    from leo.analysis.polynomial_tracklets import TrackConfig
    from leo.operations.tle_archive import TleArchiveReader

    plan = load_plan(work)
    header = work / f"{ident}-early.json"
    if sha(header) != plan["early_packet_sha256"][ident]:
        raise ValueError("first-visit packet changed")
    locked = read(header)
    if os.sched_getaffinity(0) != {plan["rows"][ident]["cpu"]} or os.nice(0) < NICE:
        raise ValueError("incorrect CPU affinity or priority")
    item = locked["track_config"]
    config = v5_direct_cavity.verified_json(item["path"], item["sha256"])["config"]
    archive = TleArchiveReader(Path(locked["archive"]))
    bound = NativeBound(validate_manifest(locked["native_manifest"], check_provider=True)["binary"])
    kwargs = dict(
        archive=archive,
        track_config=TrackConfig(**config),
        screen_center=locked["screen_center"],
        region=SearchRegion(tuple(locked["tile"])),
        library=work / "orbit_projector.so",
        bound=bound,
    )
    if sha(kwargs["library"]) != plan["library_sha256"]:
        raise ValueError("compact projector kernel changed")
    before, started, cpu = current_rss(), monotonic_ns(), process_time()
    state = None
    if mode == "early":
        state = v5_causal_startup.prepare(archive, locked["anchor"], locked["screen_center"])
    ready, prepared_rss, prepare_cpu = monotonic_ns(), current_rss(), process_time() - cpu
    signal = json.loads(sys.stdin.readline())
    delivered = monotonic_ns()
    factor = v5_direct_cavity.verified_json(signal["path"], locked["native_sha256"])
    if (
        factor["source"]["session_id"] != locked["session"]
        or factor["clock_anchor"] != locked["anchor"]
    ):
        raise ValueError("final factors disagree with the original first-visit packet")
    result = (
        v5_causal_startup.finish(factor, state, **kwargs)
        if mode == "early"
        else v5_direct_cavity.solve(factor, **kwargs)
    )
    completed = monotonic_ns()
    validate_result(result)
    if set(result["arms"]) != set(ARMS):
        raise ValueError("both calibration arms are mandatory")
    save_json(
        out,
        dict(
            result=result,
            prepare_started_ns=started,
            prepare_ready_ns=ready,
            input_released_ns=signal["release_ns"],
            input_received_ns=delivered,
            result_ready_ns=completed,
            prepare_cpu_s=prepare_cpu,
            fitted_cpu_s=process_time() - cpu - prepare_cpu,
            prep_rss_before_kib=before,
            prep_rss_ready_kib=prepared_rss,
            rss_peak_kib=getrusage(RUSAGE_SELF).ru_maxrss,
            early_stages_s=state.stages if state is not None else {},
        ),
    )


def replay(work, ident, mode):
    plan = load_plan(work)
    row = plan["rows"][ident]
    case, _request, binding = verify_input(ident)
    require_fields(row, binding)
    if sources()[0] != plan["sources"]:
        raise ValueError("the startup source differs from its own seal")
    directory = work / ident / mode
    directory.mkdir(parents=True, exist_ok=False)
    out = directory / "measurement.json"
    command = [
        "nice",
        "-n",
        str(NICE),
        "taskset",
        "-c",
        str(row["cpu"]),
        str(v5_lean.PYTHON),
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.causal_startup_replay",
        "worker",
        "--work",
        str(work),
        "--case",
        ident,
        "--mode",
        mode,
        "--result",
        str(out),
    ]
    env = direct.command_env(v5_lean.SOURCE)
    env["PYTHONPATH"] = f"{v5_lean.SOURCE}:{ROOT}"
    env["TMPDIR"] = str(work)
    begin = monotonic()
    with (directory / "worker.log").open("xb") as log:
        worker = subprocess.Popen(command, env=env, stdin=subprocess.PIPE, stdout=log, stderr=log)
        try:
            deadline = begin + LEAD
            while worker.poll() is None and monotonic() < deadline:
                sleep(min(0.2, deadline - monotonic()))
            if worker.poll() is None:
                worker.stdin.write(
                    encoded(dict(path=case["native_path"], release_ns=monotonic_ns())) + b"\n"
                )
                worker.stdin.flush()
            worker.wait(timeout=max(1, LIMIT - (monotonic() - begin)))
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
            status = "timed_out"
        else:
            status = "failed"
        finally:
            worker.stdin.close()
    if worker.returncode or not out.is_file():
        lines = (directory / "worker.log").read_text(errors="replace").splitlines()
        result = v5_lean._no_fix(lines[-1] if lines else "no worker receipt", status=status)
        result["arms"] = {a: {"latlon": None} for a in ARMS}
        save_json(out, dict(result=result))
    result = read(out)
    validate_result(result["result"])
    save_json(
        directory / "attempt.json",
        dict(
            result,
            **binding,
            id=ident,
            cpu=row["cpu"],
            mode=mode,
            launcher_wall_s=monotonic() - begin,
            log_sha256=sha(directory / "worker.log"),
            source_lock_sha256=sha(work / "plan.json"),
        ),
    )
    print(ident, mode, result["result"]["status"], result["result"].get("reason", ""), flush=True)


def run_case(work, ident):
    for mode in CASES[ident][1]:
        replay(work, ident, mode)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seal", "run", "worker"))
    parser.add_argument("--work", type=local_output, required=True)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--mode", choices=("stock", "early"))
    parser.add_argument("--result", type=local_output)
    args = parser.parse_args()
    if args.action == "seal":
        lock(args.work)
    elif args.action == "worker":
        numerical(args.work, args.case, args.mode, args.result)
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda case: run_case(args.work, case), CASES))


if __name__ == "__main__":
    main()
