"""Run four metadata-selected 2.5 MS/s saved-IQ dwells serially on ARM."""
from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import subprocess
import time
from pathlib import Path

import numpy as np

import cohort

HERE = Path(__file__).resolve().parent
INPUTS = Path("/var/tmp/leo-ds7-large-arm-20260928")
ORACLE = Path("/var/tmp/leo-arm-full-search-oracle-allrates")
BASELINE = HERE.parent / "2026_09_28_ds7_large_arm/baseline-01/rows.jsonl"
PASSWORD = Path("/home/mouse9911/gits/plutosdr-fw-glrt-deployment-review/artifacts/device-tool-glrt-ethernet/artifacts/native-lnb-20-20260910/ssh-password")
SSH_BASE = ["sudo", "-n", "sshpass", "-f", str(PASSWORD)]
SSH_OPTIONS = ["-o", "LogLevel=ERROR", "-o", "ConnectTimeout=5", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=/tmp/leo-static-arm-access/known_hosts"]
TARGET = "root@192.168.1.15"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def remote(command: str, timeout: int = 15) -> str:
    return subprocess.check_output(
        [*SSH_BASE, "ssh", *SSH_OPTIONS, TARGET, command],
        text=True,
        timeout=timeout,
    )


def upload(source: Path, destination: str) -> None:
    subprocess.run(
        [*SSH_BASE, "scp", "-O", *SSH_OPTIONS, str(source), f"{TARGET}:{destination}"],
        check=True,
        timeout=60,
    )


def select_four(rows: list[dict]) -> list[dict]:
    selected = []
    rate_rows = [row for row in rows if row["rate_hz"] == 2_500_000]
    for edge in ("lower", "upper"):
        group = [row for row in rate_rows if row["target"]["edge"] == edge]
        if len(group) < 2:
            raise ValueError(f"insufficient {edge} metadata")
        selected.extend((group[0], group[-1]))
    return selected


def baseline() -> dict[tuple[str, int], dict]:
    result = {}
    for line in BASELINE.read_text().splitlines():
        row = json.loads(line)
        context = row["context"]
        if row["method"] == "original" and row["repeat"] == 0 and row["status"] == "ok":
            result[(context["session_id"], context["visit_index"])] = {
                (probe["receiver_id"], probe["probe_index"]): probe
                for probe in row["result"]["probes"]
            }
    return result


def template_map() -> dict[str, dict]:
    oracle = json.loads((ORACLE / "oracle.json").read_text())
    return {
        case["context"]["target"]["edge"]: case["templates"]
        for case in oracle["cases"]
        if case["context"]["rate_hz"] == 2_500_000
    }


def wait_job(directory: str, pid: int, stem: str, timeout_s: int = 180) -> None:
    deadline = time.monotonic() + timeout_s
    exit_path = f"{directory}/{stem}.exit"
    while time.monotonic() < deadline:
        state = remote(
            f"if test -f {shlex.quote(exit_path)}; then echo complete; "
            f"elif kill -0 {pid} 2>/dev/null; then echo running; else echo lost; fi"
        ).strip()
        if state == "complete":
            return
        if state == "lost":
            raise RuntimeError(f"remote job {pid} vanished without an exit receipt")
        time.sleep(5)
    state = remote(
        f"if test -f {shlex.quote(exit_path)}; then echo complete; "
        f"elif kill -0 {pid} 2>/dev/null; then echo running; else echo lost; fi"
    ).strip()
    raise TimeoutError(f"remote job {pid} state after {timeout_s}s: {state}")


def run(binary: Path, unit: Path, output: Path) -> None:
    receipt = json.loads((INPUTS / "inputs.json").read_text())
    selected = select_four(receipt["rows"])
    templates = template_map()
    references = baseline()
    output.mkdir(exist_ok=False)
    raw_directory = output / "raw"
    raw_directory.mkdir()
    staging = output / "staging"
    staging.mkdir()
    remote_directory = f"/mnt/glrtbench/arm-full-opt-cohort-{int(time.time())}"
    source_hash = sha(Path(__file__))
    manifest = {
        "schema": "arm-full-optimization-arm-cohort/v1",
        "complete": False,
        "selection": "first and last lower, then first and last upper, among 2.5 MS/s rows in metadata order",
        "selected": selected,
        "inputs_manifest_sha256": sha(INPUTS / "inputs.json"),
        "baseline_sha256": sha(BASELINE),
        "oracle_sha256": sha(ORACLE / "oracle.json"),
        "runner_source_sha256": source_hash,
        "binary_sha256": sha(binary),
        "unit_binary_sha256": sha(unit),
        "remote_directory": remote_directory,
        "rf_collection": False,
        "hardware_radio_commands": False,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    remote(f"mkdir {shlex.quote(remote_directory)}")
    upload(binary, f"{remote_directory}/cohort")
    upload(unit, f"{remote_directory}/test_screen")

    local_files: dict[str, Path] = {"cohort": binary, "test_screen": unit}
    for edge, items in templates.items():
        for kind, item in items.items():
            path = ORACLE / item["file"]
            if sha(path) != item["sha256"]:
                raise ValueError(f"template hash mismatch: {path}")
            remote_name = f"{edge}-{kind}.c128"
            upload(path, f"{remote_directory}/{remote_name}")
            local_files[remote_name] = path
    remote_hashes = remote(
        f"cd {shlex.quote(remote_directory)} && sha256sum "
        + " ".join(shlex.quote(name) for name in local_files)
    )
    (output / "remote-upload-sha256.txt").write_text(remote_hashes)
    observed = {line.split()[1]: line.split()[0] for line in remote_hashes.splitlines()}
    for name, path in local_files.items():
        if observed.get(name) != sha(path):
            raise ValueError(f"remote upload hash mismatch: {name}")
    unit_output = remote(
        f"cd {shlex.quote(remote_directory)} && chmod 755 cohort test_screen && ./test_screen",
        timeout=30,
    )
    (output / "unit.stdout").write_text(unit_output)

    raw_records = []
    audits = []
    timing_rows = []
    for index, row in enumerate(selected):
        source = INPUTS / row["file"]
        if sha(source) != row["sha256"]:
            raise ValueError(f"saved-IQ hash mismatch: {source}")
        iq = np.load(source, allow_pickle=False)
        ci16 = staging / f"case-{index}.ci16"
        np.asarray(iq, dtype="<i2").tofile(ci16)
        upload(ci16, f"{remote_directory}/case-{index}.ci16")
        remote_digest = remote(f"sha256sum {shlex.quote(remote_directory + f'/case-{index}.ci16')}").split()[0]
        if remote_digest != sha(ci16):
            raise ValueError(f"remote CI16 hash mismatch: case {index}")
        edge = row["target"]["edge"]
        stem = f"case-{index}"
        command = (
            f"cd {shlex.quote(remote_directory)} && "
            f"(./cohort 2500000 {edge}-exact.c128 {edge}-control.c128 {stem}.ci16 "
            f"> {stem}.jsonl 2> {stem}.stderr; echo $? > {stem}.exit) "
            f"> /dev/null 2>&1 & echo $!"
        )
        pid = int(remote(command).strip())
        wait_job(remote_directory, pid, stem, 180)
        exit_code = int(remote(f"cat {shlex.quote(remote_directory + '/' + stem + '.exit')}").strip())
        stdout = remote(f"cat {shlex.quote(remote_directory + '/' + stem + '.jsonl')}", timeout=30)
        stderr = remote(f"cat {shlex.quote(remote_directory + '/' + stem + '.stderr')}", timeout=30)
        (raw_directory / f"{stem}.jsonl").write_text(stdout)
        (raw_directory / f"{stem}.stderr").write_text(stderr)
        rows = [json.loads(line) for line in stdout.splitlines()]
        for native in rows:
            raw_records.append({"context": row, "native": native})
        reference = references[(row["session_id"], row["visit_index"])]
        audit = cohort.compare(rows, reference) if exit_code == 0 and len(rows) == 22 else {
            "errors": [{"error": "runner_failure", "exit_code": exit_code, "row_count": len(rows)}]
        }
        audits.append({"context": row, "exit_code": exit_code, "row_count": len(rows), "audit": audit})
        for native in rows:
            timing_rows.append(native["timings_ms"])
        (output / "progress.json").write_text(json.dumps({"completed_dwells": index + 1, "planned_dwells": 4, "last_pid": pid}, indent=2) + "\n")

    with (output / "raw.jsonl").open("x") as stream:
        for record in raw_records:
            stream.write(json.dumps(record) + "\n")
    (output / "audit.json").write_text(json.dumps(audits, indent=2) + "\n")
    totals = {
        key: sum(float(row[key]) for row in timing_rows)
        for key in ("total_cpu", "coarse", "acquisition", "fine_fft", "conditioned", "verification", "glrt")
    }
    summary = {
        "schema": "arm-full-optimization-arm-cohort-summary/v1",
        "passed": all(not item["audit"]["errors"] for item in audits),
        "dwells": len(audits),
        "windows": len(raw_records),
        "reference_positive": sum(item["audit"].get("reference_positive", 0) for item in audits),
        "native_positive": sum(item["audit"].get("native_positive", 0) for item in audits),
        "matched_positive": sum(item["audit"].get("matched_positive", 0) for item in audits),
        "timing_ms_totals": totals,
        "timing_ms_per_dwell": {key: value / len(audits) for key, value in totals.items()},
        "errors": [error for item in audits for error in item["audit"]["errors"]],
        "rf_collection": False,
        "hardware_radio_commands": False,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    manifest["complete"] = True
    manifest["processed_dwells"] = len(audits)
    manifest["processed_windows"] = len(raw_records)
    manifest["raw_sha256"] = sha(output / "raw.jsonl")
    manifest["audit_sha256"] = sha(output / "audit.json")
    manifest["summary_sha256"] = sha(output / "summary.json")
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--unit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    run(arguments.binary, arguments.unit, arguments.output)
