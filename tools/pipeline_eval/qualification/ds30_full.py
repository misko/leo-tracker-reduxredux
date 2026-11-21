"""Run the frozen full-DS30 comparison on saved I/Q, with one core per recording."""

import argparse
import fcntl
import os
import socket
import tempfile
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

from ..scoring import ARMS, validate_result
from . import blind_compact_run, ds30_panel, original_v5, recording_to_v5
from .ds30_full_inputs import BULK, METHODS, OUT, WORK
from .full_v5_check import _sha
from .reverse_glrt_reference import read_bound
from .reverse_glrt_report import read
from .timing_first_position import full_identity


def verified_bytes(path, digest):
    if _sha(Path(path)) != digest.removeprefix("sha256:"):
        raise ValueError("full DS30 input or product changed: " + str(path))


def captured_input(case, method, root, build):
    """Store the measured input separately so recovering a solver never repeats acquisition."""
    path = root / "acquisition.json"
    if path.exists():
        evidence = read(path)
        if (
            evidence["build_sha256"] != _sha(OUT / "build.json")
            or evidence["input_sha256"] != case["native"]["sha256"]
        ):
            raise ValueError("incompatible acquisition receipt")
        verified_bytes(evidence["native_path"], evidence["native_sha256"])
        return evidence, False
    directory = Path(tempfile.mkdtemp(prefix="raw-", dir=root))
    start = time.monotonic()
    capture = blind_compact_run.acquire(case, method, directory, build)
    elapsed = time.monotonic() - start
    if (
        capture["raw_authority"] != case["raw_authority"]
        or capture["visits"] != case["recording"]["window_count"]
        or capture["antenna_probes"] != 2 * case["valid_visits"]
    ):
        raise ValueError("receiver did not consume the committed samples")
    receipt = dict(
        **capture,
        native_path=str(directory / "native.json"),
        acquisition_wall_s=elapsed,
        input_sha256=case["native"]["sha256"],
        build_sha256=_sha(OUT / "build.json"),
    )
    recording_to_v5.save(path, receipt)
    return receipt, True


def infer(case, method, archived, directory, root, build):
    started = time.monotonic()
    source = "archived_original_glrt" if archived else "fresh_raw"
    reference = read_bound(case["request"])
    if reference["job"]["evaluation_reference"] is not None or reference["role"] != "baseline":
        raise ValueError("expected the truth-free baseline request")
    public = dict(
        id=case["id"],
        panel="DS30",
        session_id=case["session_id"],
        regions=case["regions"],
        request_path=str(BULK / case["request"]["path"]),
        native_path=str(BULK / case["native"]["path"]),
        native_sha256="sha256:" + case["native"]["sha256"],
    )
    capture, fresh = {}, False
    if case["valid_visits"] == 0:
        result = dict(
            status="withheld",
            reason="no valid receiver windows in the sealed recording",
            boundary="hardware capture eligibility",
            metrics={},
            arms={a: {"latlon": None} for a in ARMS},
        )
        return result, dict(
            source=source,
            solver_wall_s=None,
            acquisition_wall_s=None,
            end_to_end_wall_s=None,
            raw_authority=case["raw_authority"],
            binding_sha256=case["request"]["sha256"],
            native_sha256=None,
            detector_cpu_s=None,
        )
    if not archived:
        detector = "original" if method == "algo07v5" else "cancellation"
        capture, fresh = captured_input(case, detector, root, build)
        native = Path(capture["native_path"])
        basic = directory / "native-request.json"
        public = recording_to_v5.bind_request(case, native, basic)
        bound = read(basic)
        bound["job"]["identity"]["run_id"] = full_identity(case["id"], bound)
        binding = directory / "binding.json"
        recording_to_v5.save(binding, bound)
        public["request_path"] = str(binding)
    else:
        verified_bytes(public["native_path"], public["native_sha256"])
    began = time.monotonic()
    if method == "algo07v5":
        result = original_v5.run(public, directory / "solver", "baseline")
    else:
        result = ds30_panel.repair_on_known_failure(public, directory / "solver", "secant")
    ended = time.monotonic()
    validate_result(result)
    return result, dict(
        source=source,
        solver_wall_s=ended - began,
        acquisition_wall_s=capture.get("acquisition_wall_s"),
        end_to_end_wall_s=ended - started if fresh else None,
        detector_cpu_s=capture.get("detector_cpu_s"),
        raw_authority=case["raw_authority"],
        binding_sha256=_sha(Path(public["request_path"])),
        native_sha256=public["native_sha256"],
        acquisition_reused=bool(capture) and not fresh,
    )


def one(row, cpu, reverse):
    os.sched_setaffinity(0, {cpu})
    entry = WORK / "bindings" / (row["id"] + ".json")
    record = read(entry)
    build = read(OUT / "build.json")
    if (
        record["roster_sha256"] != build["roster_sha256"]
        or row["archived_original"] != record["archived_original"]
    ):
        raise ValueError("case binding differs from the cohort")
    case = record["case"]
    if case["id"] != row["id"] or case["recording"]["window_count"] != row["windows"]:
        raise ValueError("incorrect study case")
    for method in METHODS[::-1] if reverse else METHODS:
        root = WORK / "runs" / row["id"] / method
        root.mkdir(parents=True, exist_ok=True)
        with (root / "run.lock").open("a") as guard:
            fcntl.flock(guard, fcntl.LOCK_EX)
            outcome = root / "outcome.json"
            if outcome.exists():
                r = read(outcome)
                if r["case_binding_sha256"] != _sha(entry) or r["build_sha256"] != _sha(
                    OUT / "build.json"
                ):
                    raise ValueError("incompatible saved study outcome")
                verified_bytes(r["prediction_path"], r["prediction_sha256"])
                continue
            directory = Path(tempfile.mkdtemp(prefix="solve-", dir=root))
            result, times = infer(
                case,
                method,
                row["archived_original"] and method == "algo07v5",
                directory,
                root,
                build,
            )
            prediction = directory / "prediction.json"
            recording_to_v5.save(prediction, result)
            recording_to_v5.save(
                outcome,
                dict(
                    case=row["id"],
                    method=method,
                    status=result["status"],
                    reason=result.get("reason"),
                    prediction_path=str(prediction),
                    prediction_sha256=_sha(prediction),
                    cpu=cpu,
                    case_binding_sha256=_sha(entry),
                    build_sha256=_sha(OUT / "build.json"),
                    **times,
                ),
            )
            print(
                "finished",
                row["id"],
                method,
                result["status"],
                str(result.get("reason") or "")[:160],
                flush=True,
            )


def run(cpus, only=None):
    if socket.gethostname().split(".")[0] != "gauss":
        raise ValueError("run this timing benchmark on Gauss")
    if len(set(cpus)) != len(cpus) or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose distinct available CPUs")
    build = read(OUT / "build.json")
    verified_bytes(OUT / "cohort.json", build["roster_sha256"])
    for name, library in blind_compact_run.LIBS.items():
        verified_bytes(library, build["libraries"][name])
    for edge, digest in build["assets"].items():
        verified_bytes(blind_compact_run.TWO_WORK / "embedded" / (edge + ".f32"), digest)
    roster = read(OUT / "cohort.json")["members"]
    if only:
        ids = set(only)
        roster = [r for r in roster if r["id"] in ids]
        if len(roster) != len(ids):
            raise ValueError("unknown DS30 recording")
    pending = [
        (i, r)
        for i, r in enumerate(roster)
        if not all((WORK / "runs" / r["id"] / m / "outcome.json").is_file() for m in METHODS)
    ]
    failed = []
    print("assigned", len(roster), "pending", len(pending), "cpus", cpus, flush=True)
    with ProcessPoolExecutor(max_workers=len(cpus)) as pool:
        free = list(cpus)
        live = {}
        while pending or live:
            ready = [
                (i, r) for i, r in pending if (WORK / "bindings" / (r["id"] + ".json")).exists()
            ]
            for i, row in ready[: len(free)]:
                cpu = free.pop(0)
                pending.remove((i, row))
                live[pool.submit(one, row, cpu, bool(i % 2))] = (cpu, row["id"])
            if not live:
                time.sleep(3)
                continue
            done, _ = wait(live, timeout=5, return_when=FIRST_COMPLETED)
            for future in done:
                cpu, ident = live.pop(future)
                free.append(cpu)
                try:
                    future.result()
                except Exception:
                    failed.append(ident)
                    print("infrastructure failure", ident, traceback.format_exc(), flush=True)
    if failed:
        raise RuntimeError(
            "Incomplete recordings need an infrastructure retry: " + ", ".join(failed)
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpus", required=True, type=lambda s: [int(c) for c in s.split(",")])
    parser.add_argument("--only", nargs="+", metavar="DS30-ID")
    args = parser.parse_args()
    run(args.cpus, args.only)
