"""Inventory final report bytes and explicit denominator exclusions."""
import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    exclusions = [
        ("dense simultaneous dual RX", "visit", 128, 79, "No passing same-probe dual-RX pair in six probes"),
        ("training-half broadband", "visit", 128, 82, "No passing dual-RX pair in first three probes"),
        ("full-span tracking", "receiver arc", 256, 132, "No qualifying dense receiver acquisition"),
        ("response normalization", "training-half acquired visit", 46, 6, "Numerical exception; retained in denominator"),
        ("response support", "completed visit", 40, 19, "Broadband support gate not passed"),
        ("adjacent boundary", "candidate edge", 552, 444, "Not all four endpoint receiver acquisitions pass sparse gate"),
        ("adjacent boundary", "candidate edge", 552, 9, "Phase-blind CFO compatibility gate rejected"),
    ]
    with (ROOT / "exclusions.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["analysis", "unit", "denominator", "excluded", "reason"])
        writer.writerows(exclusions)
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.name == "artifact-manifest.json":
            continue
        files.append({"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size,
                      "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (ROOT / "artifact-manifest.json").write_text(json.dumps({
        "schema": "phase-replay-report-artifacts/v1",
        "base_commit": "e1a24b200d4bb68d4f38484dc591e9b9616a2e70",
        "files": files,
        "external_source_provenance": "capture-audit/source-provenance.json",
        "external_cache_instructions": "REPRODUCE.md",
    }, indent=2) + "\n")
    print(f"Sealed {len(files)} report artifacts")


if __name__ == "__main__":
    main()
