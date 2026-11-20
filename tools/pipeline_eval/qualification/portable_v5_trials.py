"""Bind and score the portable compact-v5 receiver without runtime site labels."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import (
    DEFAULT_OUT,
    ROOT,
    THREAD_ENV,
    encoded,
    local_output,
    public_cases,
    references,
    run_one,
    save_json,
)
from ..scoring import validate_result
from ..variants import orbit_projector, portable_v5, v5_core, v5_lean
from .full_v5_check import BULK, _load_case

REPORT = ROOT / "reports/2026_11_19_receiver_screening/portable-v5"
WORKER = Path(__file__).with_name("portable_v5_worker.py")
NATIVE = v5_lean.SOURCE.parent.parent / "native-001/manifest.json"
ROOF_CASE = "DS26-0036"
METHOD = portable_v5.METHOD
CASE_S = 300
SOURCE_SNAPSHOT_ENV = "LEO_PORTABLE_V5_SOURCE_SNAPSHOT"


def checksum(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def adapter_source(path):
    """Resolve the measured adapter bytes for an explicit historical replay."""
    snapshot = os.environ.get(SOURCE_SNAPSHOT_ENV)
    if snapshot and path.name in {"portable_v5.py", WORKER.name}:
        return Path(snapshot).expanduser().resolve() / f"{path.name}.txt"
    return path


def verify_frozen_source():
    source = v5_lean.SOURCE
    files = {
        str(p.relative_to(source)): "sha256:" + checksum(p)
        for p in sorted((source / "leo").rglob("*"))
        if p.is_file() and p.suffix in {".py", ".so", ".h", ".c", ".inc"}
    }
    digest = hashlib.sha256(encoded(files)).hexdigest()
    if f"sha256:{digest}" != v5_lean.SOURCE_SHA256:
        raise ValueError("the frozen v5 numerical source has changed")
    return digest


def source_lock():
    modules = (portable_v5, v5_core, v5_lean, orbit_projector)
    paths = (WORKER, orbit_projector.KERNEL, NATIVE, *(Path(m.__file__) for m in modules))
    lock = {p.name: checksum(adapter_source(p)) for p in paths}
    lock["frozen-scientific-source"] = verify_frozen_source()
    return lock


def sandbox(cpu, objects, kernel):
    python = Path(sys.executable)
    base, prefix = Path(sys.base_prefix), Path(sys.prefix)
    alias = (python.parent / python.readlink()).parent.parent if python.is_symlink() else base
    bindings = [
        ("/usr", "/usr"),
        ("/lib", "/lib"),
        ("/lib64", "/lib64"),
        (str(base), str(base)),
        (str(prefix), str(prefix)),
        (str(v5_lean.SOURCE), str(v5_lean.SOURCE)),
        (str(NATIVE.parent), str(NATIVE.parent)),
        (str(adapter_source(WORKER)), "/worker/main.py"),
        (str(kernel), "/kernel/projector.so"),
    ]
    if str(alias) != str(base):
        bindings.append((str(base), str(alias)))
    packages = "/worker/tools/pipeline_eval/variants"
    for module in (portable_v5, v5_core, v5_lean, orbit_projector):
        path = Path(module.__file__)
        bindings.append((str(adapter_source(path)), packages + "/" + path.name))
    bindings.extend((str(path), f"/history/{digest}.tle") for digest, path in objects.items())
    command = [
        "taskset",
        "-c",
        str(cpu),
        "bwrap",
        "--unshare-all",
        "--die-with-parent",
        "--clearenv",
        "--tmpfs",
        "/tmp",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--chdir",
        "/tmp",
        "--setenv",
        "HOME",
        "/tmp",
        "--setenv",
        "PYTHONPATH",
        f"{v5_lean.SOURCE}:/worker",
    ]
    for name, value in THREAD_ENV.items():
        command.extend(("--setenv", name, value))
    for source, target in bindings:
        command.extend(("--ro-bind", source, target))
    return [*command, str(python), "-B", "/worker/main.py", str(NATIVE)]


def preferred_history(entries, cutoff):
    allowed = [
        r for r in entries if cutoff - 72 * portable_v5.NS_HOUR <= r["collected_utc_ns"] <= cutoff
    ]
    return sorted(allowed, key=lambda r: (r["collected_utc_ns"], r["sha256"]))


def portable_trial(ident, mode, document, offer, history, objects, kernel, cpu, deadline, **extra):
    data = encoded(dict(document=document, tile=offer, history=history, **extra))
    start = perf_counter()
    try:
        result = json.loads(
            subprocess.run(
                sandbox(cpu, objects, kernel),
                input=data,
                capture_output=True,
                check=True,
                timeout=deadline,
            ).stdout
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        result = portable_v5.unavailable((exc.stderr or b"").decode(errors="replace")[-2400:])
        result["status"] = "timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed"
        if not result["reason"]:
            result["reason"] = f"portable worker {result['status']}"
    validate_result(result)
    row = dict(
        id=ident,
        method=METHOD,
        mode=mode,
        offer=offer,
        result=result,
        cpu=cpu,
        worker_wall_s=perf_counter() - start,
        input_sha256=hashlib.sha256(data).hexdigest(),
        document_sha256=hashlib.sha256(encoded(document)).hexdigest(),
        history_sha256=hashlib.sha256(encoded(history)).hexdigest(),
    )
    print(ident, mode, result["status"], round(row["worker_wall_s"], 2), flush=True)
    return row


def authentic_roof():
    frozen = _load_case(ROOF_CASE)
    request_file = BULK / frozen["request"]["path"]
    if checksum(request_file) != frozen["request"]["sha256"]:
        raise ValueError("roof parity request digest changed")
    request = json.loads(request_file.read_bytes())
    job = request["job"]
    actual = job["native_input"]
    track = job["track_config"]
    if (
        job["evaluation_reference"] is not None
        or request["native_manifest"] != json.loads(NATIVE.read_bytes())
        or request["source"]["sha256"] != v5_lean.SOURCE_SHA256
        or checksum(actual["path"]) != actual["sha256"].removeprefix("sha256:")
        or actual["sha256"].removeprefix("sha256:") != frozen["native"]["sha256"]
        or checksum(track["path"]) != track["sha256"].removeprefix("sha256:")
        or json.loads(Path(track["path"]).read_bytes())["config"] != portable_v5.TRACK_CONFIG
    ):
        raise ValueError("portable and roof controls must share the exact inferential inputs")
    document = json.loads(Path(actual["path"]).read_bytes())
    history, objects = [], {}
    for filename, digest in request["causal_snapshots"].items():
        time, file_digest = Path(filename).stem.split("-", 1)
        path = Path(job["tle_root"]) / "archive/space-track" / filename
        if file_digest != digest or checksum(path) != digest:
            raise ValueError("roof causal history binding changed")
        history.append(dict(collected_utc_ns=int(time), sha256=digest))
        objects[digest] = path
    offer = dict(id="original", center=job["search_center"], width_km=25.0)
    cutoff = document["clock_anchor"]["before"]["realtime_ns"]
    retained = preferred_history(history, cutoff)
    panel, ref = references("ds26-common127", [ROOF_CASE])
    (stock_case,) = public_cases(panel, ref, DEFAULT_OUT / "inputs")
    return document, offer, retained, objects, job["screen_center"], stock_case


def roof_parity(scratch, report, kernel, cpus, deadline):
    document, offer, history, objects, screen, stock_case = authentic_roof()
    with ThreadPoolExecutor(max_workers=2) as pool:
        stock = pool.submit(run_one, "orbit_projector", stock_case, scratch, deadline, cpus[1])
        generic = pool.submit(
            portable_trial,
            ROOF_CASE,
            "roof-parity",
            document,
            offer,
            history,
            objects,
            kernel,
            cpus[0],
            deadline,
            screen_center=screen,
        )
        original, portable = stock.result(), generic.result()
    fields = ("observations", "tracks", "initial_branches", "initial_arm_fits", "cavity_offered")
    a, b = original["result"], portable["result"]
    same = (
        a["status"] == b["status"] == "ok"
        and a["arms"] == b["arms"]
        and all(a["metrics"][k] == b["metrics"][k] for k in fields)
    )
    save_json(report / "roof-parity.json", dict(identical=same, stock=original, portable=portable))
    return same


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, default=Path("/tmp/leo-portable-v5"))
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--cpus", type=int, nargs=2, default=(4, 5))
    args = parser.parse_args()
    cpus = args.cpus
    if len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        parser.error("choose two distinct available CPUs")
    scratch, report = local_output(args.scratch), local_output(args.report)
    scratch.mkdir(parents=True, exist_ok=True)
    save_json(report / "source-lock.json", source_lock())
    kernel = scratch / "orbit_projector.so"
    orbit_projector.compile_kernel(kernel)
    if not roof_parity(scratch, report, kernel, cpus, CASE_S):
        raise ValueError("portable implementation failed authentic roof parity")


if __name__ == "__main__":
    main()
