"""Retain bounded non-IQ receipts and scientific PNGs for this local checkpoint."""

from __future__ import annotations

import gzip
import json
import platform
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from leo.contracts.digests import canonical_json_bytes, sha256_digest

ROOT = Path(__file__).resolve().parents[3]
RAW = Path("/tmp/leo-adaptive-overview.HLsKuK")
DESTINATION = Path(__file__).parent
FIGURES = ROOT / "reports/figures/2026_09_09_adaptive_overview"


def retain(path: Path, payload: bytes) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"refusing changed evidence: {path}")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": len(payload),
        "sha256": sha256_digest(payload),
    }


def test_counts(path: Path) -> dict:
    document = ET.parse(path).getroot()
    suites = [document] if document.tag == "testsuite" else document.findall("testsuite")
    return {
        key: sum(int(s.get(key, "0")) for s in suites)
        for key in ("tests", "failures", "errors", "skipped")
    }


def main() -> None:
    checks = json.loads((RAW / "final-corrected/final-checks.json").read_text())
    if len(checks) != 7 or any(r["returncode"] for r in checks):
        raise ValueError("final checks did not all succeed")
    python = test_counts(RAW / "final-corrected/python-final.xml")
    web = test_counts(RAW / "final-corrected/web-final.xml")
    if any(counts[key] for counts in (python, web) for key in ("failures", "errors", "skipped")):
        raise ValueError("final test failures/errors/skips remain")
    full = json.loads((RAW / "full-overview-corrected/summary.json").read_text())
    if full["passed_candidates"] != 806432 or not full["status"]["overview"]["association_count"]:
        raise ValueError("full-scale association rendering was not verified")
    saved = json.loads((RAW / "saved-overviews-corrected/summary.json").read_text())
    if len(saved["rows"]) != 6 or any(
        run["result"]["newly_analyzed_visits"] != 0 or run["result"]["overview_state"] != "ready"
        for row in saved["rows"]
        for run in row["cli"]
    ):
        raise ValueError("saved-metrics render/resume smoke did not close")
    artifacts = []
    files = [
        *RAW.glob("*.log"),
        *RAW.glob("*.xml"),
        *RAW.glob("*.py"),
        *RAW.glob("final-checks.json"),
        *RAW.glob("final-corrected/*"),
        RAW / "full-overview/summary.json",
        RAW / "full-overview-corrected/summary.json",
        RAW / "saved-overviews/summary.json",
        RAW / "positive-overviews/summary.json",
        *RAW.glob("positive-overviews/*-product.json.gz"),
        *RAW.glob("positive-overviews/*-cli-*.json"),
        *RAW.glob("saved-overviews-corrected/*.json"),
        *RAW.glob("saved-overviews-corrected/*.stdout"),
        *RAW.glob("saved-overviews-corrected/*.stderr"),
    ]
    for source in sorted(set(files)):
        if not source.is_file() or source.stat().st_size > 10_000_000:
            raise ValueError(f"unexpected receipt source: {source}")
        payload = source.read_bytes()
        relative = source.relative_to(RAW)
        if source.suffix != ".gz":
            relative = Path(str(relative) + ".gz")
            payload = gzip.compress(payload, mtime=0)
        artifacts.append(retain(DESTINATION / relative, payload))
    for folder, prefix in (
        (RAW / "saved-overviews-corrected", ""),
        (RAW / "full-overview-corrected", ""),
    ):
        for source in sorted(folder.glob("*.png")):
            artifacts.append(retain(FIGURES / (prefix + source.name), source.read_bytes()))
    changed = subprocess.check_output(
        ["git", "ls-files", "--modified", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    sources = sorted(
        {p for p in changed if p.startswith(("src/", "tests/", "web/src/"))}
        | {
            "src/leo/scanner/detector.py",
            "src/leo/analysis/starlink/trajectories.py",
            "src/leo/presentation/persistent_hop_analysis.py",
            "web/package-lock.json",
            "docs/architecture/adaptive-scanner-implementation.md",
            "reports/2026_09_09_adaptive_overview_checkpoint.md",
            str(Path(__file__).resolve().relative_to(ROOT)),
        }
    )
    index = {
        "checkpoint": "actual-visit-overview-progress-api-ui-offline-v1",
        "parent_head": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "remote_main_fetched": subprocess.check_output(
            ["git", "rev-parse", "origin/main"], text=True
        ).strip(),
        "source_hashes": {p: sha256_digest((ROOT / p).read_bytes()) for p in sources},
        "python": platform.python_version(),
        "environment": {"OPENBLAS_NUM_THREADS": "1", "PYTHONDONTWRITEBYTECODE": "1"},
        "raw_directory": str(RAW),
        "checks": checks,
        "tests": {"python": python, "web": web},
        "artifacts": artifacts,
        "scope": [
            "No radio, FPGA, firmware, kernel, production or remote push changed.",
            "Six saved RX1 dwells; RX0, receipts and other fixture visits are synthetic.",
            "Two positive cases are score-selected from an opened development corpus.",
            "Full-span maximum-candidate stress uses analytic metadata, not IQ.",
            "Store status benchmark excludes capture-manifest lookup and HTTP/browser work.",
            "No independent detection, ARM-load, live-duty, TLE or multi-channel-ID claim.",
        ],
    }
    retain(DESTINATION / "index.json", canonical_json_bytes(index))
    print(
        json.dumps(
            {
                "tests": index["tests"],
                "artifacts": len(artifacts),
                "source_files": len(sources),
                "bytes": sum(a["bytes"] for a in artifacts),
            }
        )
    )


if __name__ == "__main__":
    main()
