"""Collect FP32 proposals and compare them with frozen FP64 proposal rows."""

import argparse
import hashlib
import ast
import json
import math
import struct
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / "2026_09_29_arm_lag_discovery"
INPUTS = Path("/var/tmp/leo-ds7-large-arm-20260928")
ORACLE = Path("/var/tmp/leo-arm-full-search-oracle-allrates")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def npy_payload(path: Path) -> bytes:
    data = path.read_bytes()
    assert data[:6] == b"\x93NUMPY"
    major = data[6]
    if major == 1:
        header_size, offset = struct.unpack_from("<H", data, 8)[0], 10
    else:
        header_size, offset = struct.unpack_from("<I", data, 8)[0], 12
    header = ast.literal_eval(data[offset : offset + header_size].decode("latin1"))
    assert header["descr"] == "<i2" and not header["fortran_order"]
    payload = data[offset + header_size :]
    assert len(payload) == 2 * math.prod(header["shape"])
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="collect the full 704-context corpus")
    args = parser.parse_args()
    reference_name = "ds7-704-v1" if args.full else "ds7-32-v1"
    output = HERE / ("host704-v1" if args.full else "host32-v1")
    output.mkdir(exist_ok=False)
    binary = HERE / "builds/host-v1/proposal_probe"
    receipt = json.loads((binary.parent / "build.json").read_text())
    assert sha(binary) == receipt["binary_sha256"]
    reference_path = OLD / reference_name / "rows.jsonl"
    rows = [json.loads(line) for line in reference_path.read_text().splitlines()]
    expected = {(r["context"]["ordinal"], r["window"], r["rx"]): r for r in rows}
    contexts = {r["context"]["ordinal"]: r["context"] for r in rows}
    oracle = json.loads((ORACLE / "oracle.json").read_text())
    templates = {}
    for case in oracle["cases"]:
        metadata = case["templates"]["exact"]
        template = ORACLE / metadata["file"]
        assert sha(template) == metadata["sha256"]
        templates[(case["context"]["rate_hz"], case["context"]["target"]["edge"])] = template
    mismatches = []
    checked = 0
    timings = []
    proposal_rows = []
    controls = []
    positive_epochs = fp64_covered = fp32_covered = 0
    with tempfile.TemporaryDirectory(prefix="leo-fp32-host-") as temp:
        raw_path = Path(temp) / "dwell.ci16"
        for rate in sorted({c["rate_hz"] for c in contexts.values()}):
            template = templates[(rate, "lower")]
            dwell = rate * 120 // 1000
            control_payloads = {
                "zero": bytes(dwell * 8),
                "full_scale_alternating": struct.pack("<hhhhhhhh", 32767, -32768, -32768, 32767, -32768, 32767, 32767, -32768) * (dwell // 2),
            }
            for name, payload in control_payloads.items():
                raw_path.write_bytes(payload)
                command = [str(binary), str(rate), str(template), str(raw_path), "--combined-only"]
                actual = [json.loads(line) for line in subprocess.run(command, check=True, text=True, capture_output=True).stdout.splitlines()]
                assert len(actual) == 22
                assert all(len(row["top4"]["combined"]) <= 4 for row in actual)
                controls.append({"rate_hz": rate, "input": name, "windows": len(actual), "complete": True})
        for ordinal, context in sorted(contexts.items()):
            source = INPUTS / context["file"]
            assert sha(source) == context["sha256"]
            payload = npy_payload(source)
            raw_path.write_bytes(payload)
            template = templates[(context["rate_hz"], context["target"]["edge"])]
            command = [str(binary), str(context["rate_hz"]), str(template), str(raw_path), "--combined-only"]
            stdout = subprocess.run(command, check=True, text=True, capture_output=True).stdout
            actual = [json.loads(line) for line in stdout.splitlines()]
            assert len(actual) == 22
            for row in actual:
                key = (ordinal, row["probe_index"], row["receiver_id"])
                want = expected[key]["ranked_epochs"]["combined"][:4]
                got = row["top4"]["combined"]
                for epoch in expected[key]["original_positive_epochs"]:
                    positive_epochs += 1
                    fp64_covered += any(abs(epoch - candidate) <= 2 for candidate in want)
                    fp32_covered += any(abs(epoch - candidate) <= 2 for candidate in got)
                checked += 1
                timings.append(row["timings_ms"]["total"])
                proposal_rows.append({"context": context, "window": key[1], "rx": key[2], "ranked_epochs": {"combined": got}})
                if got != want:
                    mismatches.append({"ordinal": ordinal, "rate_hz": context["rate_hz"], "window": key[1], "rx": key[2], "fp64": want, "fp32": got})
    result = {
        "complete": True,
        "scope": "host FP32 candidate-rank parity only; no GLRT scoring or hardware timing",
        "binary_sha256": sha(binary),
        "reference_rows_sha256": sha(reference_path),
        "contexts": len(contexts),
        "windows": checked,
        "rates_hz": sorted({c["rate_hz"] for c in contexts.values()}),
        "top4_mismatches": len(mismatches),
        "original_positive_epochs": positive_epochs,
        "fp64_radius2_covered_hits": fp64_covered,
        "fp32_radius2_covered_hits": fp32_covered,
        "mean_host_cpu_ms_per_window": sum(timings) / len(timings),
        "controls": controls,
        "mismatches": mismatches,
    }
    rows_path = output / "rows.jsonl"
    rows_path.write_text("".join(json.dumps(row) + "\n" for row in proposal_rows))
    result["rows_sha256"] = sha(rows_path)
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k != "mismatches"}, indent=2))


if __name__ == "__main__":
    main()
