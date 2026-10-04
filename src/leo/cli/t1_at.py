"""Composition root for the prepared-evidence T1-AT adaptive analysis stage.

Use through ``python -m leo.cli.adaptive_hop_analysis --session-id SCAN
--t1-at-discovery-input INPUT.json --t1-at-maximum-seconds 600`` with the same
``--probe-stride-ms`` used to generate the bound analysis manifest. The discovery
manifest is T1AtDiscoveryManifestV1, alongside its hashed prediction-bank.npz.
It contains qualified orbit-blind refined candidates and frozen receiver/RF
calibration; discovery scans the entire supplied near-visible orbit bank.
``--t1-at-input`` instead accepts a T1AtInputV1 with matched RF-arm timing modes.

This stage does not generate/refit calibration or collect new RF data. It runs
only after adaptive metrics are complete, and writes candidate-only products to
the requested tracking root. Existing analysis defaults remain unchanged.
"""

from pathlib import Path

from leo.application.t1_at import T1AtService
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore
from leo.storage.t1_at import T1AtDiscoveryFile, T1AtInputFile, T1AtProductStore


def run(
    *,
    capture_root: Path,
    analysis_root: Path,
    output_root: Path,
    prepared_input: Path | None = None,
    discovery_input: Path | None = None,
    session_id: str,
    maximum_seconds: float = 120,
    probe_stride_ms: int = 120,
) -> dict:
    if (prepared_input is None) == (discovery_input is None):
        raise ValueError("provide exactly one T1-AT prepared or discovery input")
    inputs = ScannerTrackingInputStore(
        capture_root, adaptive_analysis_root=analysis_root, adaptive_probe_stride_ms=probe_stride_ms
    )
    try:
        capture = inputs.load(session_id)
        product = T1AtService(
            inputs=T1AtInputFile(prepared_input)
            if prepared_input is not None
            else T1AtDiscoveryFile(discovery_input),
            products=T1AtProductStore(output_root),
        ).run(capture, maximum_seconds=maximum_seconds)
    finally:
        inputs.close()
    return dict(
        state="complete",
        baseline_id=product.baseline_id,
        prepared_input_sha256=product.prepared_input_sha256,
        coverage={
            arm: dict(
                assigned=r.final.assigned,
                denominator=r.final.denominator,
                unassigned=r.final.unassigned,
                satellites=len(r.final.satellites),
            )
            for arm, r in product.arms.items()
        },
        candidate_only=True,
        identity_claimed=False,
    )
