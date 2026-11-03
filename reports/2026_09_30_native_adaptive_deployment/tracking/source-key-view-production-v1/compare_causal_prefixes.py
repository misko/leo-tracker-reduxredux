"""Compare promoted production tracking with its frozen owning-key control."""

import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[4]
REPORT = Path(__file__).resolve().parent
SOURCE = ROOT / "reports/2026_09_30_native_adaptive_deployment/tracking/candidates.tsv"
CONTROL = Path("/var/tmp/leo-source-key-view/control/tracking")
PROMOTED = Path("/var/tmp/leo-source-key-production/host/leo-tracking")
SCRATCH = Path("/var/tmp/leo-source-key-production/prefix.tsv")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


lines = SOURCE.read_text().splitlines()
rows = sorted((line.split("\t") for line in lines[1:]),
              key=lambda row: (int(row[8]), row[0]))
first, last = int(rows[0][8]), int(rows[-1][8])
cutoff = first
results = []
started = time.monotonic()
while cutoff < last:
    cutoff = min(cutoff + 5_000_000_000, last)
    selected = [row for row in rows if int(row[8]) <= cutoff]
    SCRATCH.write_text(lines[0] + "\n" +
                       "\n".join("\t".join(row) for row in selected) + "\n")
    outputs = []
    for binary in (CONTROL, PROMOTED):
        remaining = 180.0 - (time.monotonic() - started)
        if remaining <= 0.0:
            raise TimeoutError("180-second causal-prefix budget exhausted")
        outputs.append(subprocess.run(
            [str(binary), str(SCRATCH)], check=True, capture_output=True,
            timeout=min(30.0, remaining)).stdout)
    if outputs[0] != outputs[1]:
        raise AssertionError(f"serialized tracking mismatch at {cutoff}")
    results.append({"cutoff_ns": cutoff, "candidates": len(selected),
                    "output_sha256": hashlib.sha256(outputs[0]).hexdigest()})

receipt = {
    "schema": "leo-tracking-source-key-view-production-prefix-parity/v1",
    "input_sha256": digest(SOURCE),
    "control_binary_sha256": digest(CONTROL),
    "promoted_binary_sha256": digest(PROMOTED),
    "comparison": "byte-identical complete public CLI output",
    "prefixes": results,
    "elapsed_seconds": time.monotonic() - started,
}
(REPORT / "causal-prefix-parity.json").write_text(
    json.dumps(receipt, indent=2) + "\n")
print(f"PASS: {len(results)} causal prefixes exact")
