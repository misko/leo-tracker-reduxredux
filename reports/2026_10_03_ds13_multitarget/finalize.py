"""Seal the review inputs/outputs and distinguish completed from deferred work."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def main():
    tests = [ROOT/"test_common.py", ROOT/"test_review.py", ROOT/"activity/test_activity_model.py",
             ROOT/"history/test_mht.py", ROOT/"tracklet/test_tracklet.py"]
    command = [sys.executable, "-m", "pytest", "-q", *map(str, tests)]
    tested = subprocess.run(command, cwd=REPO, text=True, capture_output=True, timeout=60)
    if tested.returncode:
        raise RuntimeError(tested.stdout+tested.stderr)
    comparisons = json.loads((ROOT/"comparison.json").read_text())
    controls = json.loads((ROOT/"controls.json").read_text())
    # Detect stale output after a worker rerun, rather than silently publishing it.
    for path, expected in {**comparisons["sources"], **controls["source_hashes"]}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Regenerate review for changed worker artifact: {path}")
    files = list(ROOT.rglob("*.py")) + [ROOT/p for p in (
        "comparison.json", "comparison.csv", "tracks.csv", "controls.json", "rf-comparison.csv",
        "scan-a-timelines.png", "scan-b-timelines.png", "key-track-residuals.png", "rf-control/receipt.json")]
    receipt = {
        "status": "bounded Stage A prototype comparison complete; Stage B not run",
        "scope": "Two scans, frozen reference physical fit, positive retained GLRT groups, selected NORAD bank; retrospective in-sample diagnostic",
        "tests": dict(command=command, returncode=tested.returncode, stdout=tested.stdout, stderr=tested.stderr),
        "completed": ["Three parallel SOL prototypes and a joint-MAP baseline",
                      "Exact peak exclusivity/alias-copy checks and synthetic multi-target tests",
                      "Per-method temporal-state controls; MHT beam-width check",
                      "Matched c=0 versus fitted-c reference-position refits and all-method reruns",
                      "Same-assignment RF comparison, timelines, key residuals, per-track metrics"],
        "not_completed": ["Complete probe opportunity ledger / observed-empty-window model",
                          "Training-only nuisance refits with blocked held-out scoring",
                          "Method-specific position searches / position accuracy comparison",
                          "Independent validation of NORAD identities or temporal-state priors"],
        "canonical_history_results": ["history/results/beam32-state", "history/results/beam8-state",
                                      "history/results/beam32-state-off", "history/results/rf-fitted-c",
                                      "history/results/rf-zero-c"],
        "superseded_history_results": ["history/results/receipt.json", "history/results/beam64-state",
                                       "history/results/*-assignments.csv (top-level exploratory files)"],
        "ui": {"dashboard": "http://gauss:8090/", "per_scan_ui_deeplinks_supported": False,
               "A_record_json": "http://gauss:8090/api/v3/scanner/adaptive-sessions/scan-fw-911c4e5db9243281",
               "B_record_json": "http://gauss:8090/api/v3/scanner/adaptive-sessions/scan-fw-ffa1cc19d8d7c09f"},
        "source_and_artifact_sha256": {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    (ROOT/"run-receipt.json").write_text(json.dumps(receipt, indent=2)+"\n")
    print(tested.stdout)
    print(receipt["status"])


if __name__ == "__main__": main()
