"""Compare frozen cohort windows against deployed native GLRT, sequentially."""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from profile_algo07_glrt import PROFILE  # noqa: E402
from stage_native_glrt_runtime import digest, verify, verify_files  # noqa: E402


def run(candidate, fixtures, output, *, build_filename="fractional-probe.json"):
    candidate = candidate.resolve(strict=True)
    output = output.resolve()
    if output.exists() or not output.is_relative_to("/srv/bulk/leo/research"):
        raise ValueError("New private output required")
    if build_filename not in ("fractional-probe.json", "schedule-probe.json"):
        raise ValueError("Unknown probe receipt")
    build_path = candidate / build_filename
    build_pin = digest(build_path)
    build = json.loads(build_path.read_text())
    base = Path(build["base"])
    script = ROOT / "reports/2026_11_03_algo07_runtime_iteration005/paired_windows.py"
    output.mkdir(parents=True)
    summaries = []
    for fixture in fixtures:
        fixture = fixture.resolve(strict=True)
        verify(base, build["base_pin"])
        verify_files(candidate, build["files_sha256"])
        before = PROFILE.verify(fixture / "frozen.json")
        if not before["verified"]:
            raise ValueError("Fixture changed")
        name = fixture.name
        command = [sys.executable, "-B", str(script), "--fixture", str(fixture),
                   "--base", str(base), "--candidate", str(candidate),
                   "--output", str(output / (name + ".json"))]
        began = time.time_ns()
        child = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 text=True, start_new_session=True)
        try:
            log, _ = child.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            log, _ = child.communicate()
            (output / (name + ".log")).write_text(log)
            raise
        (output / (name + ".log")).write_text(log)
        verify(base, build["base_pin"])
        verify_files(candidate, build["files_sha256"])
        after = PROFILE.verify(fixture / "frozen.json")
        if not after["verified"] or digest(build_path) != build_pin:
            raise ValueError("Frozen fixture or build changed during comparison")
        receipt = dict(command=command, exit_code=child.returncode, started_utc_ns=began,
                       ended_utc_ns=time.time_ns(), timeout_seconds=180,
                       fixture_before=before, fixture_after=after,
                       source_bytes_verified=True, build_receipt_sha256=build_pin,
                       script_sha256=digest(script), driver_sha256=digest(Path(__file__)))
        (output / (name + "-verification.json")).write_text(json.dumps(receipt, indent=2) + "\n")
        if child.returncode:
            raise RuntimeError("Paired comparison failed: " + name)
        paired = json.loads((output / (name + ".json")).read_text())
        summary = dict(fixture=name, windows=len(paired["rows"]),
                       exact=paired["all_receiver_outputs_exact"], totals=paired["totals"],
                       speedup=paired["totals"]["baseline"] / paired["totals"]["candidate"])
        summaries.append(summary)
        print(json.dumps(summary), flush=True)
    (output / "summary.json").write_text(json.dumps(summaries, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True, action="append")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-receipt", default="fractional-probe.json",
                        choices=("fractional-probe.json", "schedule-probe.json"))
    args = parser.parse_args()
    run(args.candidate, args.fixture, args.output, build_filename=args.build_receipt)
