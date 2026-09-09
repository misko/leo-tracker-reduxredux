"""Archive this bounded offline checkpoint; no IQ, executables or external writes."""

from __future__ import annotations

import gzip
import importlib.metadata
import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from leo.contracts.digests import canonical_json_bytes, sha256_digest
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1
from leo.scanner.adaptive_hop_products import AdaptiveHopAnalysisBindingV1
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = Path(__file__).resolve().parent
RAW = Path("/tmp/leo-adaptive-analysis.g6WLQT")
SOURCES = (
    "pyproject.toml",
    "src/leo/application/adaptive_hop_analysis.py",
    "src/leo/cli/adaptive_hop_analysis.py",
    "src/leo/scanner/adaptive_hop_analysis.py",
    "src/leo/scanner/adaptive_hop_products.py",
    "src/leo/storage/adaptive_hop_analysis.py",
    "src/leo/storage/adaptive_hop_analysis_source.py",
    "src/leo/storage/analysis_worker_lock.py",
    "src/leo/storage/persistent_hop_analysis_v2.py",
    "tests/application/test_adaptive_hop_analysis.py",
    "tests/cli/test_adaptive_hop_analysis_cli.py",
    "tests/scanner/test_adaptive_hop_analysis.py",
    "tests/scanner/test_adaptive_hop_products.py",
    "tests/scanner/test_adaptive_hop_saved_parity_tool.py",
    "tests/storage/test_adaptive_hop_analysis.py",
    "tests/storage/test_adaptive_hop_analysis_source.py",
    "tests/storage/test_analysis_worker_lock.py",
    "tools/qualify_adaptive_hop_analysis.py",
)
NUMERICAL_REFERENCES = (
    "src/leo/scanner/detector.py",
    "src/leo/scanner/persistent_hop_analysis.py",
    "src/leo/analysis/starlink/acquisition.py",
    "src/leo/analysis/starlink/pilot_methods.py",
    "src/leo/analysis/starlink/templates.py",
    "tools/evaluate_presence_window_rank.py",
)
TESTS = (
    "tests/scanner/test_adaptive_hop_analysis.py",
    "tests/scanner/test_adaptive_hop_products.py",
    "tests/scanner/test_adaptive_hop_saved_parity_tool.py",
    "tests/scanner/test_adaptive_hop_contracts.py",
    "tests/scanner/test_adaptive_hop_application.py",
    "tests/scanner/test_adaptive_hop_history.py",
    "tests/scanner/test_adaptive_glrt_publication.py",
    "tests/scanner/test_adaptive_scan.py",
    "tests/scanner/test_persistent_hop_analysis.py",
    "tests/scanner/test_persistent_hop_standard_analysis.py",
    "tests/scanner/test_persistent_hop_contracts.py",
    "tests/storage/test_adaptive_hop_analysis_source.py",
    "tests/storage/test_adaptive_hop_analysis.py",
    "tests/storage/test_analysis_worker_lock.py",
    "tests/storage/test_adaptive_hop_history.py",
    "tests/storage/test_adaptive_hop_store.py",
    "tests/storage/test_adaptive_hop_queue.py",
    "tests/storage/test_persistent_hop_analysis_store.py",
    "tests/storage/test_persistent_hop_analysis_store_v2.py",
    "tests/storage/test_scanner_glrt_store.py",
    "tests/application/test_adaptive_hop_analysis.py",
    "tests/cli/test_adaptive_hop_analysis_cli.py",
    "tests/cli/test_adaptive_hop_schedule.py",
    "tests/cli/test_adaptive_hop_supervisor.py",
    "tests/cli/test_persistent_hop_schedule.py",
    "tests/cli/test_scanner_glrt_runtime.py",
    "tests/api/test_adaptive_hop_history_api.py",
    "tests/api/test_persistent_hop_history_api.py",
    "tests/api/test_scanner_glrt_api.py",
)


def write_new(name, data):
    path = OUTPUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"refuse to replace differing checkpoint evidence: {name}")
    else:
        with path.open("xb") as stream:
            stream.write(data)
    return {"path": name, "bytes": len(data), "sha256": sha256_digest(data)}


def main():
    artifacts = []
    for name in (
        "core.xml",
        "analysis-first.xml",
        "analysis-second.xml",
        "analysis-third.xml",
        "analysis-final.xml",
        "analysis-final.log",
    ):
        artifacts.append(write_new(name + ".gz", gzip.compress((RAW / name).read_bytes(), mtime=0)))
    suites = ET.parse(RAW / "analysis-final.xml").getroot().findall("testsuite")
    counts = {
        key: sum(int(s.get(key, "0")) for s in suites)
        for key in ("tests", "errors", "failures", "skipped")
    }
    if counts != {"tests": 674, "errors": 0, "failures": 0, "skipped": 0}:
        raise ValueError("final regression receipt does not establish the expected checkpoint")
    replay = RAW / "saved-parity-storage-final"
    summary = json.loads((replay / "summary.json").read_text())
    if len(summary["rows"]) != 4:
        raise ValueError("saved parity inventory is incomplete")
    for row in summary["rows"]:
        for name, digest in row["artifacts"].items():
            payload = (replay / name).read_bytes()
            if sha256_digest(payload) != digest:
                raise ValueError("parity numerical artifact changed")
            artifacts.append(write_new("saved-parity/" + name, payload))
        for run in range(3):
            name = f"fixture-{row['rate_hz']}-{row['edge']}-cli-{run}.json"
            payload = (replay / name).read_bytes()
            if json.loads(payload)["exit_code"]:
                raise ValueError("saved-IQ command line execution failed")
            artifacts.append(
                write_new("saved-parity/" + name + ".gz", gzip.compress(payload, mtime=0))
            )
        bulk = Path(row["storage_cli"]["temporary_synthetic_capture_root"])
        captures, products = (
            AdaptiveHopIqStore(bulk, read_only=True),
            AdaptiveHopAnalysisStore(bulk, read_only=True),
        )
        try:
            session_id = row["storage_cli"]["cli_runs"][0]["session_id"]
            capture = captures.verify(session_id)
            if capture.manifest_sha256 != row["storage_cli"]["synthetic_capture_manifest_sha256"]:
                raise ValueError("synthetic saved-IQ capture changed")
            binding = AdaptiveHopAnalysisBindingV1(
                input_manifest_sha256=capture.manifest_sha256,
                receipt=capture.manifest.receipt,
                configuration=AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=row["rate_hz"]),
            )
            with products.job(binding) as job:
                manifest = job.verify()
                if (
                    manifest is None
                    or manifest.binding_sha256 != row["storage_cli"]["metrics_binding_sha256"]
                ):
                    raise ValueError("saved-IQ metrics are not sealed")
                name = f"saved-parity/{row['rate_hz']}-{row['edge']}-metrics-manifest.json.gz"
                artifacts.append(
                    write_new(
                        name,
                        gzip.compress(
                            canonical_json_bytes(manifest.model_dump(mode="json")), mtime=0
                        ),
                    )
                )
        finally:
            products.close()
            captures.close()
    artifacts.append(
        write_new(
            "saved-parity/summary.json.gz",
            gzip.compress((replay / "summary.json").read_bytes(), mtime=0),
        )
    )
    commands = [
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            *[p for p in SOURCES if p.endswith(".py")],
            str(Path(__file__).relative_to(ROOT)),
        ],
        [
            sys.executable,
            "-m",
            "mypy",
            "--python-version=3.12",
            "--follow-imports=silent",
            *[p for p in SOURCES if p.startswith("src/")],
        ],
        ["git", "diff", "--check"],
    ]
    static = []
    for i, command in enumerate(commands):
        result = subprocess.run(
            command, cwd=ROOT, capture_output=True, text=True, timeout=60, check=False
        )
        receipt = {
            "command": command,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        artifacts.append(
            write_new(f"static-{i}.json.gz", gzip.compress(canonical_json_bytes(receipt), mtime=0))
        )
        static.append(receipt)
        if result.returncode:
            raise ValueError(f"static check failed: {result.stdout}{result.stderr}")
    source_hashes = {
        p: sha256_digest((ROOT / p).read_bytes()) for p in (*SOURCES, *NUMERICAL_REFERENCES)
    }
    index = {
        "checkpoint": "adaptive-actual-visit-fractional-metrics-offline-v1",
        "parent_head": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "remote_main_fetched": subprocess.check_output(
            ["git", "rev-parse", "origin/main"], cwd=ROOT, text=True
        ).strip(),
        "raw_directory": str(RAW),
        "source_hashes": source_hashes,
        "test_command": [
            sys.executable,
            "-m",
            "pytest",
            *TESTS,
            f"--junitxml={RAW}/analysis-final.xml",
            "-q",
            "--tb=short",
        ],
        "saved_iq_command": [
            sys.executable,
            "-m",
            "tools.qualify_adaptive_hop_analysis",
            "--source",
            summary["source"],
            "--output",
            str(replay),
        ],
        "saved_iq_process_wall_bound_seconds": 600,
        "environment": {
            "python": sys.version,
            **{
                k: importlib.metadata.version(k)
                for k in ("numpy", "pydantic", "zstandard", "pytest", "mypy", "ruff")
            },
            "PYTHONPATH": os.environ.get("PYTHONPATH"),
            "OPENBLAS_NUM_THREADS": os.environ.get("OPENBLAS_NUM_THREADS"),
        },
        "tests": counts,
        "static": static,
        "artifacts": artifacts,
        "numerical_parity": {
            k: sum(r[k] for r in summary["rows"])
            for k in (
                "candidates",
                "fractional_complete",
                "unavailable",
                "integer_vs_fractional_winner_changes",
            )
        },
        "scope_limits": [
            "saved RX1 plus explicitly synthetic zero RX0/receipt/other visits",
            "development numerical parity, not an independent sensitivity holdout",
            "no ARM, new RF, firmware, FPGA, production restart, deployment or remote push",
            "dense metrics only; automatic backfill, plots and UI progress remain unintegrated",
        ],
    }
    write_new("index.json", canonical_json_bytes(index))
    print(
        json.dumps(
            {
                "tests": counts,
                "archived_artifacts": len(artifacts),
                "source_hashes": len(source_hashes),
                "numerical_parity": index["numerical_parity"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
