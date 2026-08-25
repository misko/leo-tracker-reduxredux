from __future__ import annotations

import hashlib
import json
from pathlib import Path

from leo.analysis.research.doppler_dataset_policy import load_doppler_dataset_policy
from leo.analysis.research.doppler_holdout_manifest import (
    load_derived_holdout_manifest,
    load_holdout_protocol,
    validate_derived_holdout_manifest,
)

ROOT = Path(__file__).parents[2]
OUTPUT = ROOT / "reports" / "figures" / "2026_08_25_doppler_holdout_feasibility"
REPORT = ROOT / "reports" / "2026_08_25_doppler_holdout_feasibility.md"
POLICY = ROOT / "config" / "analysis" / "doppler-experiment-dataset-policy-v1.json"
PROTOCOL = ROOT / "config" / "analysis" / "doppler-holdout-feasibility-protocol-v1.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_committed_feasibility_evidence_is_closed_and_response_blind() -> None:
    policy = load_doppler_dataset_policy(POLICY)
    protocol = load_holdout_protocol(PROTOCOL.read_bytes())
    payload = (OUTPUT / "derived-manifest.json").read_bytes()
    manifest = load_derived_holdout_manifest(payload)

    validate_derived_holdout_manifest(manifest, protocol, policy)

    assert manifest.protocol_repository_commit == ("c6d0654aebd294745ef87416a5e5b5b503d17c01")
    assert manifest.capture_count == 15
    assert manifest.evaluable_capture_count == 4
    assert manifest.minimum_evaluable_capture_count == 10
    assert manifest.launch_gate == "fail"
    assert manifest.future_odd_qin_outcomes_opened is False
    assert manifest.candidate_estimators_run is False
    assert manifest.odd_qin_symbols_demodulated_or_scored is False
    assert len(manifest.captures) == 15
    assert sum(len(item.scopes) for item in manifest.captures) == 60
    assert sum(len(scope.products) for item in manifest.captures for scope in item.scopes) == 300
    assert all(item.episode is not None for item in manifest.captures)
    text = payload.decode("utf-8")
    for forbidden in (
        "odd_absolute_cfo_hz",
        "odd_residual_cfo_hz",
        "odd_frequency_uncertainty_hz",
        "odd_error",
    ):
        assert forbidden not in text


def test_committed_artifact_receipts_and_plain_png_are_exact() -> None:
    artifact_manifest = json.loads((OUTPUT / "artifact-manifest.json").read_text())
    for artifact in artifact_manifest["artifacts"].values():
        path = OUTPUT / artifact["path"]
        assert path.stat().st_size == artifact["bytes"]
        assert _sha256(path) == artifact["sha256"]

    png = (OUTPUT / "feasibility-accounting.png").read_bytes()
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert int.from_bytes(png[16:20], "big") == 2295
    assert int.from_bytes(png[20:24], "big") == 935
    report = REPORT.read_text(encoding="utf-8")
    assert "launch gate failed: 4 of 15 captures were evaluable" in report
    assert "feasibility-accounting.png" in report
