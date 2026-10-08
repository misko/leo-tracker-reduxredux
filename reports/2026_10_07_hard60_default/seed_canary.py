"""Transfer verified numerical checkpoints through ports; never copy publications.

The standard production queue still renders and publishes the result and PNG.
Usage: seed_canary.py QUALIFICATION_ROOT PRODUCTION_ROOT SESSION RECEIPT
"""

import json
import sys
from pathlib import Path

import numpy as np

from leo.application.hard60_runner import Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore


def main(source_root, target_root, session, receipt_path):
    source_root, target_root = Path(source_root), Path(target_root)
    status = Hard60Store(source_root).status(session)
    if status.manifest is None:
        raise ValueError("qualification is incomplete")
    doc = status.manifest.document
    if doc.configuration_sha256 != canonical_digest(configuration()):
        raise ValueError("qualification uses different code or configuration")
    inputs = ScannerTrackingInputStore(target_root)
    try:
        source = inputs.load(session)
    finally:
        inputs.close()
    assert source.input_manifest_sha256 == doc.input_manifest_sha256
    assert source.analysis_manifest_sha256 == doc.analysis_manifest_sha256
    assert Hard60Store(target_root).status(session).state == "pending"
    binding = doc.diagnostics["checkpoint_binding"]
    reader = RegionalCheckpointStore(source_root, session, binding)
    writer = RegionalCheckpointStore(target_root, session, binding)
    config_key = canonical_digest(json_value(Hard60Configuration()))
    keys = [f"point:{p.east_km:g}:{p.north_km:g}" for p in doc.methods[0].points]
    for basin in doc.diagnostics["retained_basins"]:
        prefix = f"point:{basin['east_km']:g}:{basin['north_km']:g}"
        keys += [prefix + ":calibration", prefix + ":association"]
        keys += [
            f"{prefix}:{arm}:{start}"
            for arm in ("zero-c", "fitted-c")
            for start in Hard60Configuration().final_starts
        ]
    slopes = []
    transferred = []

    def check_fit(fitted):
        vector = np.asarray(fitted["vector"])
        slopes.extend(vector[[3, 5]].tolist())
        assert max(abs(vector[[3, 5]])) <= 60 + 1e-6
        assert fitted["converged"] == (fitted["stationarity"] <= 0.001)

    with writer.writer():
        for key in keys:
            full = config_key + ":" + key
            receipt = reader.get(full)
            if receipt is None:
                continue
            result = receipt["result"]
            if result and "fits" in result:
                check_fit(result["fits"]["V16"]["fit"])
            elif result and "prefit" in result:
                check_fit(result["prefit"])
                check_fit(result["postfit"])
            elif result and "vector" in result:
                check_fit(result)
            writer.put(full, receipt)
            assert writer.get(full) == receipt
            transferred.append({"key": key, "sha256": canonical_digest(receipt)})
    assert len(doc.methods[0].points) == 400
    assert all(arm.selected and arm.selected.converged for arm in doc.methods[0].arms)
    output = {
        "session_id": session,
        "configuration_sha256": doc.configuration_sha256,
        "checkpoint_binding": binding,
        "checkpoint_count": len(transferred),
        "maximum_absolute_stage_slope_hz_s": max(abs(np.asarray(slopes))),
        "finished_document_copied": False,
        "png_copied": False,
        "checkpoints": transferred,
    }
    Path(receipt_path).write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps({k: v for k, v in output.items() if k != "checkpoints"}))


if __name__ == "__main__":
    main(*sys.argv[1:])
