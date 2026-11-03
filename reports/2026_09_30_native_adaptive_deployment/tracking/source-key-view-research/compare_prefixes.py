"""Compare independent control/research public CLI outputs on causal DS9 prefixes."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

base = Path(__file__).resolve().parent
source = base.parent / "candidates.tsv"
lines = source.read_text().splitlines()
rows = sorted((line.split("\t") for line in lines[1:]), key=lambda r: (int(r[8]), r[0]))
first, last = int(rows[0][8]), int(rows[-1][8])
cutoff = first
results = []
started = time.monotonic()
scratch = Path("/var/tmp/leo-source-key-view/prefix.tsv")
while cutoff < last:
    cutoff = min(cutoff + 5_000_000_000, last)
    selected = [r for r in rows if int(r[8]) <= cutoff]
    scratch.write_text(lines[0] + "\n" + "\n".join("\t".join(r) for r in selected) + "\n")
    outputs = []
    for mode in ("control", "research"):
        remaining = 180 - (time.monotonic() - started)
        if remaining <= 0:
            raise TimeoutError("180-second diagnostic budget exhausted")
        outputs.append(subprocess.run(
            [f"/var/tmp/leo-source-key-view/{mode}/tracking", str(scratch)],
            check=True, capture_output=True, timeout=min(30, remaining)).stdout)
    if outputs[0] != outputs[1]:
        raise AssertionError(f"serialized tracking mismatch at cutoff {cutoff}")
    results.append({"cutoff_ns": cutoff, "candidates": len(selected),
                    "output_sha256": hashlib.sha256(outputs[0]).hexdigest()})
(base / "prefix-parity.json").write_text(json.dumps({
    "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    "comparison": "byte-identical complete public CLI output",
    "prefixes": results, "elapsed_seconds": time.monotonic() - started,
}, indent=2) + "\n")
print(f"PASS: {len(results)} causal prefixes exact")
