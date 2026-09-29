#!/usr/bin/env python3
"""Verify build receipts and the bounded scientific-semantics claim."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parent / "2026_09_29_arm_fine_precision/builds/host-raw-v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


checks = []
for receipt_path in sorted((ROOT / "builds").glob("*/*/build-receipt.json")):
    receipt = json.loads(receipt_path.read_text())
    directory = receipt_path.parent
    for name, digest in receipt["binaries"].items():
        checks.append((f"binary:{receipt['variant']}:{receipt['target']}:{name}", sha(directory / name) == digest))
    for name, digest in receipt["sources"].items():
        checks.append((f"source:{receipt['variant']}:{receipt['target']}:{name}", sha(directory / name) == digest))
    command_text = " ".join(" ".join(record["command"]) for record in receipt["commands"])
    checks.append((f"no-fast-math:{receipt['variant']}:{receipt['target']}",
                   "-fno-fast-math" in command_text and "-ffast-math" not in command_text))
    checks.append((f"distinct-test:{receipt['variant']}:{receipt['target']}",
                   f"test_fine_precision_{receipt['variant'].replace('-', '_')}_{receipt['target']}" in receipt["binaries"]))
    if receipt["target"] != "arm":
        checks.append((f"unit-executed:{receipt['variant']}:{receipt['target']}",
                       receipt["unit"]["executed"] and "passed:" in receipt["unit"]["stdout"]))

for snapshot in ("strict-base", "fine-local", "fine-local-v2", "combined-v2", "limited-complex-v2"):
    for name in ("full_search.c", "src/native_presence/presence.c"):
        checks.append((f"final-glrt-unchanged:{snapshot}:{name}",
                       sha(ROOT / "sources" / snapshot / name) == sha(BASE / name)))

for snapshot in ("fine-local-v2", "combined-v2", "limited-complex-v2"):
    header = (ROOT / "sources" / snapshot / "fine_precision.h").read_text()
    checks.append((f"explicit-16-byte-alignment:{snapshot}",
                   "posix_memalign(&storage,16,bytes)" in header))
    checks.append((f"matching-spectrum-free:{snapshot}",
                   "free(cache->entries[i].spectra[frame])" in header))

result = {
    "schema": "arm-compile-pack-audit/v1",
    "passed": all(ok for _, ok in checks),
    "checks": [{"name": name, "passed": ok} for name, ok in checks],
}
(ROOT / "audit.json").write_text(json.dumps(result, indent=2) + "\n")
if not result["passed"]:
    raise SystemExit("audit failed")
