"""Run the frozen paired stock and family-local cavity measurements."""

import argparse
import json
import os
import signal
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, validate_result
from ..variants import orbit_projector, v5_core, v5_lean, v5_optional_cavity, v5_secant_fit
from . import phase_confirmation
from .portable_gate_trials import checksum, compressed_rows

OUT = corpus.REPO / "reports/2026_11_19_receiver_screening/deployment/optional-cavity"
DIAGNOSED = ("DS26-0191", "DS26-0199", "DS26-0046")
SALT = "optional-cavity-controls-v1:"
STOCK = "v5_secant_fit"
METHOD = v5_optional_cavity.METHOD
CPUS = (8, 9, 10, 11)
CAP_S = 170


def source():
    paths = [
        Path(m.__file__)
        for m in (orbit_projector, v5_core, v5_lean, v5_optional_cavity, v5_secant_fit)
    ]
    paths.extend((orbit_projector.KERNEL, Path(__file__), OUT / "PROTOCOL.md"))
    return dict(
        files={p.name: checksum(p) for p in paths},
        science=v5_lean.SOURCE_SHA256,
        family_science=v5_optional_cavity.FAMILY_SHA256,
    )


def roster(work):
    shared = phase_confirmation.frozen_inputs()
    excluded = set(DIAGNOSED) | set(phase_confirmation.TIMING_IDS)
    excluded.update(r for group in phase_confirmation.confirmation_ids(shared) for r in group)
    controls = sorted(
        shared.keys() - excluded, key=lambda ident: sha256((SALT + ident).encode()).hexdigest()
    )[:3]
    _, digests = corpus._selection("ds26-all159")
    archive = corpus._index(corpus._read_frozen("inputs.jsonl", digests))
    result = []
    for idx, ident in enumerate((*DIAGNOSED, *controls)):
        item = shared.get(ident) or archive[ident]
        case = corpus._public(item, corpus.DEFAULT_BULK, corpus.DEFAULT_BLIND, work / "inputs")
        native, catalogue = Path(case["native_path"]), Path(case["catalog_path"])
        if (
            checksum(native) != item["native"]["sha256"]
            or checksum(catalogue) != item["catalog"]["sha256"]
        ):
            raise ValueError("the recorded native input digest changed")
        request = json.loads(Path(case["request_path"]).read_bytes())
        job = request["job"]
        recent = max(
            (int(name.split("-")[0]), digest.removeprefix("sha256:"))
            for name, digest in request["causal_snapshots"].items()
            if int(name.split("-")[0]) < item["cutoff_utc_ns"]
        )
        if (
            request["source"]["sha256"] != v5_lean.SOURCE_SHA256
            or job["evaluation_reference"] is not None
            or job["search_center"] != item["regions"][0]["center"]
            or job["native_input"]["sha256"] != case["native_sha256"]
            or recent != (item["catalog_timestamp_ns"], item["catalog"]["sha256"])
        ):
            raise ValueError("inference request differs from the authenticated original offer")
        result.append(
            (
                case,
                dict(
                    id=ident,
                    recording=ident,
                    condition="diagnosed" if ident in DIAGNOSED else "control",
                    native_sha256=item["native"]["sha256"],
                    catalog_sha256=item["catalog"]["sha256"],
                    frozen_request_sha256=item["request"]["sha256"],
                    tile=item["regions"][0],
                    track_config_sha256=item["track_config"]["sha256"],
                    cpu=CPUS[idx % len(CPUS)],
                ),
            )
        )
    return result


def invoke(method, case, receipt, scratch, timeout):
    began = perf_counter()
    scratch.mkdir()
    request, output = scratch / "input.json", scratch / "measurement.json"
    save_json(request, case)
    timing = scratch / "time.txt"
    command = [
        "taskset",
        "-c",
        str(receipt["cpu"]),
        "/usr/bin/time",
        "-f",
        "%U %S %M",
        "-o",
        str(timing),
        sys.executable,
        "-B",
        "-m",
        "tools.pipeline_eval.qualification.optional_cavity_trial",
        "--child",
        method,
        str(request),
        str(output),
    ]
    with (scratch / "run.log").open("wb") as log:
        proc = subprocess.Popen(
            command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            proc.wait(timeout=timeout)
            status, reason = "failed", f"worker exit {proc.returncode}"
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()
            status, reason = "timed_out", f"worker exceeded {timeout:.1f} s"
    if proc.returncode == 0 and output.is_file():
        result = json.loads(output.read_bytes())
        if result["status"] == "unavailable" and (result.get("reason") or "").startswith(
            "ValueError:"
        ):
            result["status"] = "failed"
    else:
        result = dict(
            status=status,
            reason=reason,
            boundary=v5_optional_cavity.BOUNDARY,
            arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            metrics={},
        )
    validate_result(result)
    usage = timing.read_text().split() if timing.is_file() else []
    user, sys_cpu, peak = map(float, usage[-3:]) if len(usage) >= 3 else (None, None, None)
    row = dict(
        receipt,
        method=method,
        result=result,
        worker_wall_s=perf_counter() - began,
        cpu_s=user + sys_cpu if user is not None else None,
        peak_rss_kib=peak,
    )
    save_json(scratch / "row.json", row)
    print(
        receipt["id"],
        method,
        result["status"],
        row["worker_wall_s"],
        result.get("reason"),
        flush=True,
    )
    return row


def child(method, request, output):
    folder = Path(request).parent / "engine"
    case = json.loads(Path(request).read_bytes())
    result = (
        v5_optional_cavity.run(case, folder)
        if method == METHOD
        else v5_secant_fit.run(case, folder, "secant")
    )
    save_json(Path(output), result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path)
    parser.add_argument("--child", nargs=3)
    args = parser.parse_args()
    if args.child:
        child(*args.child)
        return
    if os.nice(0) < 10 or not set(CPUS) <= os.sched_getaffinity(0):
        raise ValueError("run on the authorized CPU roster at nice 10 or lower priority")
    work = local_output(args.work)
    work.mkdir(exist_ok=False, parents=True)
    started = perf_counter()
    plan = roster(work)
    frozen = source()
    save_json(
        OUT / "plan.json",
        dict(source=frozen, cases=[r for _, r in plan], salt=SALT, cap_s=CAP_S, total_seconds=600),
    )

    def lane(i):
        rows = []
        for case, one in plan[i :: len(CPUS)]:
            choices = (METHOD, STOCK) if i % 2 == 0 else (STOCK, METHOD)
            limit = max(1.0, min(CAP_S, (595 - (perf_counter() - started)) / 2))
            for method in choices:
                rows.append(invoke(method, case, one, work / f"{one['id']}-{method}", limit))
        return rows

    with ThreadPoolExecutor(len(CPUS)) as pool:
        positions = [r for group in pool.map(lane, range(len(CPUS))) for r in group]
    if source() != frozen:
        raise ValueError("sources changed during the paired run")
    raw = OUT / "paired.jsonl.gz"
    write(raw, compressed_rows(positions))
    save_json(
        OUT / "prediction-lock.json",
        dict(
            files={p.name: checksum(p) for p in (OUT / "plan.json", raw)},
            wall_s=perf_counter() - started,
        ),
    )


if __name__ == "__main__":
    main()
