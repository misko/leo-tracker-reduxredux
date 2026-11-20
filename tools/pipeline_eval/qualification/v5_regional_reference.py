"""Private arbitrary-tile entry for the frozen original v5 numerical worker."""

import argparse
import gzip
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from time import perf_counter
from unittest.mock import patch
from uuid import uuid4

from ..variants import v5_lean

REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / "reports/2026_11_19_receiver_screening/receiver-core/v5-regional-reference"
ROOF = "DS29-0082"
ROOF_SOURCE = REPO / "reports/2026_11_18_pipeline_eval/predictions/roof16/v5_lean.jsonl.gz"
CPU, LIMIT, MEMORY = 23, 240, 3 * 1024**3
METHOD = "v5_original_regional_reference"
METRICS = (
    "native_observations",
    "tracks",
    "c0_associated_observations",
    "fitted_c_associated_observations",
    "c0_conditional_rms_hz",
    "fitted_c_conditional_rms_hz",
    "c0_frequency_score",
    "fitted_c_frequency_score",
    "stages",
)


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def checked(path, expected):
    result = sha(path)
    if result != expected.removeprefix("sha256:"):
        raise ValueError(f"digest changed for {path}")
    return result


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def coordinate(values):
    if (
        not isinstance(values, list)
        or len(values) != 2
        or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
        or not -90 < values[0] < 90
        or not -180 <= values[1] <= 180
    ):
        raise ValueError("valid offered latitude and longitude required")
    return values


def scientific_domain(center, screen):
    latitude, longitude = coordinate(center)
    screen_lon = coordinate(screen)[1]
    half_width = v5_lean.ROOF_WIDTH_KM / 2
    half_lon = half_width / (111.32 * math.cos(math.radians(latitude)))
    if (
        abs(latitude) + half_width / 111 >= 90
        or abs(longitude) + half_lon >= 180
        or abs(longitude - screen_lon) + half_lon >= 180
    ):
        raise ValueError("offered 25 km tile crosses the pole or local longitude seam")


def offered_validator(original):
    def validate(job):
        scientific_domain(job["search_center"], job["screen_center"])
        # The production validator uses this value solely to protect its fixed
        # presentation frame. Keep its complete contract and restore the offer
        # before any native inputs, screen or fit are constructed.
        original(dict(job, search_center=list(v5_lean.ROOF_CENTER)))
        return job

    return validate


def cgroup_metrics():
    group = next(
        line[3:]
        for line in Path("/proc/self/cgroup").read_text().splitlines()
        if line.startswith("0::")
    )
    root = Path("/sys/fs/cgroup") / group.lstrip("/")
    cpu_s = (
        int(
            dict(line.split() for line in (root / "cpu.stat").read_text().splitlines())[
                "usage_usec"
            ]
        )
        * 1e-6
    )
    return dict(
        cgroup=group,
        cpu_affinity=sorted(os.sched_getaffinity(0)),
        nice=os.nice(0),
        cpu_s=cpu_s,
        memory_peak_bytes=int((root / "memory.peak").read_text()),
        memory_limit_bytes=int((root / "memory.max").read_text()),
        swap_limit_bytes=int((root / "memory.swap.max").read_text()),
    )


def worker(request_path, result_path):
    from leo.operations import localization_v3_job as job

    if not Path(job.__file__).is_relative_to(v5_lean.SOURCE):
        raise ValueError("job validator was imported outside the original runtime")
    started = cgroup_metrics()
    if (
        started["cpu_affinity"] != [CPU]
        or started["memory_limit_bytes"] != MEMORY
        or started["swap_limit_bytes"] != 0
        or started["nice"] < 10
    ):
        raise ValueError("private reference lacks its declared process bounds")
    write(result_path.parent / "start.json", started)
    with patch.object(job, "validate_request", offered_validator(job.validate_request)):
        v5_lean._worker(request_path, result_path)
    write(result_path.parent / "finish.json", cgroup_metrics())


def run_request(request, work, *, blind_dir=None):
    work.mkdir(parents=True, exist_ok=False)
    scratch = work / "tmp"
    scratch.mkdir()
    request["job"]["output_root"] = str(work)
    request_path, result_path = work / "request.json", work / "result.json"
    write(request_path, request)
    unit = "leo-v5-regional-" + uuid4().hex[:12]
    command = [
        "systemd-run",
        "--user",
        "--wait",
        f"--unit={unit}",
        f"--property=MemoryMax={MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=TimeoutStopSec=4s",
        "--property=KillMode=control-group",
        "--property=Nice=10",
        f"--property=StandardOutput=append:{work / 'stages.log'}",
        "--property=StandardError=inherit",
        f"--working-directory={REPO}",
        f"--setenv=TMPDIR={scratch}",
        f"--setenv=PYTHONPATH={v5_lean.SOURCE}:{v5_lean.RUNNER}:{REPO}",
        *(
            f"--setenv={name}=1"
            for name in (
                "OPENBLAS_NUM_THREADS",
                "MKL_NUM_THREADS",
                "OMP_NUM_THREADS",
                "BLIS_NUM_THREADS",
            )
        ),
        "taskset",
        "-c",
        str(CPU),
        "bwrap",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--bind",
        str(work),
        str(work),
    ]
    if blind_dir is not None:
        command.extend(("--tmpfs", str(blind_dir)))
    command.extend(
        (
            str(v5_lean.PYTHON),
            "-B",
            "-m",
            "tools.pipeline_eval.qualification.v5_regional_reference",
            "worker",
            str(request_path),
            str(result_path),
        )
    )
    began = perf_counter()
    with (work / "service.log").open("xb") as log:
        try:
            code = subprocess.run(
                command, stdout=log, stderr=log, timeout=LIMIT + 12, check=False
            ).returncode
        except subprocess.TimeoutExpired:
            subprocess.run(["systemctl", "--user", "kill", "--signal=KILL", unit], check=False)
            code = None
    service = (work / "service.log").read_text(errors="replace")
    completed = code == 0 and result_path.is_file() and (work / "finish.json").is_file()
    if completed:
        result = read(result_path)
    else:
        state = "timed_out" if code is None or "result: timeout" in service else "failed"
        result = v5_lean._no_fix(state + " in original v5 numerical service", status=state)
    logs = work / "stages.log"
    events = []
    if logs.is_file():
        for line in logs.read_text(errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("event") in ("stage", "recovery_stage"):
                events.append(event)
    # The existing v5 endpoint renderer stores RF on the original metric keys.
    for arm, endpoint in result["arms"].items():
        value = result["metrics"].get(f"{arm}_conditional_rms_hz")
        if value is not None:
            endpoint["rf_rms_hz"] = value
    row = dict(
        result=result,
        method=METHOD,
        wall_s=perf_counter() - began,
        exit_code=code,
        request_sha256=sha(request_path),
        service=service,
        events=events,
        resources={
            name: read(work / f"{name}.json")
            for name in ("start", "finish")
            if (work / f"{name}.json").is_file()
        },
    )
    if logs.is_file():
        row["stage_log_sha256"] = sha(logs)
        if not completed:
            row["failure_log_tail"] = logs.read_text(errors="replace").splitlines()[-12:]
    return row


def roof_request():
    from .full_v5_check import BULK, _load_case

    case = _load_case(ROOF)
    path = BULK / case["request"]["path"]
    checked(path, case["request"]["sha256"])
    request = read(path)
    job = request["job"]
    checked(Path(job["native_input"]["path"]), case["native"]["sha256"])
    if job["search_center"] != case["regions"][0]["center"]:
        raise ValueError("authentic offered roof tile differs")
    return request, case


def parity(measured, archived):
    same = dict(
        status=measured["status"] == archived["status"] == "ok",
        coordinates={
            arm: measured["arms"].get(arm, {}).get("latlon") == archived["arms"][arm]["latlon"]
            for arm in v5_lean.ARMS
        },
        counters={key: measured["metrics"].get(key) == archived["metrics"][key] for key in METRICS},
    )
    return dict(
        same, exact=all((same["status"], *same["coordinates"].values(), *same["counters"].values()))
    )


def roof(root):
    request, case = roof_request()
    lock = dict(
        case=ROOF,
        cpu=CPU,
        limit_s=LIMIT,
        memory_bytes=MEMORY,
        capture_era_request_sha256=case["request"]["sha256"],
        archive_prediction_sha256=sha(ROOF_SOURCE),
        frozen_source_sha256=v5_lean.SOURCE_SHA256,
        frozen_runner_sha256=v5_lean.RUNNER_SHA256,
        worker_sha256=sha(Path(v5_lean.__file__)),
        adapter_sha256=sha(Path(__file__)),
    )
    write(REPORT / "roof-plan.json", lock)
    outcome = run_request(request, root)
    result = REPORT / "roof-prediction.json"
    write(result, outcome)
    write(
        REPORT / "roof-prediction-lock.json",
        {path.name: sha(path) for path in (REPORT / "roof-plan.json", result)},
    )
    checked(ROOF_SOURCE, lock["archive_prediction_sha256"])
    (archive,) = (
        row
        for row in map(json.loads, gzip.decompress(ROOF_SOURCE.read_bytes()).splitlines())
        if row["id"] == ROOF
    )
    write(REPORT / "roof-parity.json", parity(outcome["result"], archive["result"]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_subparsers(dest="mode", required=True)
    child = mode.add_parser("worker")
    child.add_argument("request", type=Path)
    child.add_argument("result", type=Path)
    roof_parser = mode.add_parser("roof")
    roof_parser.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.mode == "worker":
        worker(args.request, args.result)
    else:
        root = args.root.resolve()
        if root.is_relative_to("/mnt/qnap01"):
            raise ValueError("QNAP is read-only")
        roof(root)


if __name__ == "__main__":
    main()
