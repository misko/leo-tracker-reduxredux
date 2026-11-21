"""Compare the active five-refresh compact v5 on the same recorded acquisition factors."""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from ..variants import v5_secant_fit
from . import recording_to_v5
from .full_v5_check import BULK, _load_case, _sha
from .reverse_glrt_reference import CASES, read_bound
from .reverse_glrt_report import read
from .timing_first_position import full_identity
from .timing_first_trial import SCRATCH as FIRST
from .two_carrier_position import POLICIES
from .two_carrier_roster import WORK

INPUTS = ("original", "single", *POLICIES)


def compact(job):
    ident, mode, cpu, root = job
    os.sched_setaffinity(0, {cpu})
    case = _load_case(ident)
    directory = root / "compact" / mode / ident
    directory.mkdir(parents=True, exist_ok=True)
    if mode == "original":
        native = BULK / case["native"]["path"]
        expected = case["native"]["sha256"]
    elif mode == "single":
        folder = FIRST / "position" / ident
        native = folder / "native.json"
        expected = read(folder / "capture-receipt.json")["new_native_sha256"]
    else:
        native = root / mode / ident / "native.json"
        expected = read(root / "captures" / ident / "capture.json")["inputs"][mode]["native_sha256"]
    if _sha(native) != expected:
        raise ValueError("compact input differs from raw replay")
    request = directory / "binding.json"
    if not request.exists():
        recording_to_v5.bind_request(case, native, directory / "basic.json")
        doc = read(directory / "basic.json")
        doc["job"]["identity"]["run_id"] = full_identity(ident, doc)
        recording_to_v5.save(request, doc)
    req = read(request)
    original = read_bound(case["request"])
    if (
        req["job"]["native_input"]["sha256"] != "sha256:" + expected
        or req["job"]["evaluation_reference"] is not None
        or any(
            req[k] != original[k]
            for k in ("source", "policy", "model", "causal_snapshots", "native_manifest")
        )
        or any(
            req["job"][k] != original["job"][k]
            for k in ("track_config", "search_center", "screen_center", "tle_root")
        )
    ):
        raise ValueError("compact geometry, calibration or input provenance changed")
    output = directory / "prediction.json"
    if not output.exists():
        public = dict(
            id=ident,
            panel=case["panel"],
            regions=case["regions"],
            session_id=case["session_id"],
            native_path=str(native),
            native_sha256="sha256:" + expected,
            request_path=str(request),
        )
        p = v5_secant_fit.run(public, directory / "solver", "secant")
        recording_to_v5.save(output, p)
    result = read(output)
    print("compact", mode, ident, result["status"], flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--work", type=Path, default=WORK)
    p.add_argument("--cpus", type=int, nargs="+", default=[9, 11, 13, 15, 17])
    a = p.parse_args()
    pairs = [(case, m) for m in INPUTS for case in CASES]
    with ProcessPoolExecutor(max_workers=len(a.cpus)) as pool:
        list(
            pool.map(
                compact,
                [(case, m, a.cpus[i % len(a.cpus)], a.work) for i, (case, m) in enumerate(pairs)],
            )
        )
