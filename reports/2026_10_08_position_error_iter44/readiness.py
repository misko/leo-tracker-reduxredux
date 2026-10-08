"""Verify final DS18 receipt and inspect every dataset member through public stores."""

import hashlib
import json
from pathlib import Path

from leo.application.hard60_runner import Hard60Configuration
from leo.contracts.digests import canonical_digest
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
AUTHORITY = Path(
    "/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds18_post_ds17/local"
)


def main():
    output = HERE / "readiness.json"
    if output.exists():
        raise FileExistsError("Preserve initial readiness snapshot")
    manifest_sha = hashlib.sha256((AUTHORITY / "manifest.json").read_bytes()).hexdigest()
    assert manifest_sha == "894a6f4b7055e5f6bd602f94ce3acf7f722f204c68c2b521a06dfd6be35a7516"
    seal = json.loads((AUTHORITY / "seal.json").read_text())
    for name, digest in seal["files"].items():
        assert "sha256:" + hashlib.sha256((AUTHORITY / name).read_bytes()).hexdigest() == digest, (
            name
        )
    members = json.loads(
        (REPORTS / "2026_10_08_position_error_iter43/membership.json").read_text()
    )["members"]
    root = Path("/srv/bulk/leo")
    store = Hard60Store(root)
    inputs = ScannerTrackingInputStore(root)
    from dataclasses import asdict

    expected_config = json.loads(json.dumps(asdict(Hard60Configuration())))
    rows = []
    try:
        for member in members:
            row = dict(member=member, baseline_status="unavailable", input_status="not_checked")
            try:
                status = store.status(member["session_id"])
                row["store_state"] = status.state
                if status.manifest is not None:
                    doc = status.manifest.document.model_dump(mode="json")
                    row["configuration_matches"] = doc["configuration"]["run"] == expected_config
                    row["recording_digest_matches"] = (
                        doc["input_manifest_sha256"] == member["recording_manifest_sha256"]
                        if member["recording_manifest_sha256"]
                        else None
                    )
                    row["document_digest"] = canonical_digest(doc)
                    row["baseline_status"] = (
                        "compatible"
                        if row["configuration_matches"] and row["recording_digest_matches"]
                        else "binding_review_required"
                    )
                    row["baseline_arms"] = {
                        a["name"]: a["selected"] for a in doc["methods"][0]["arms"]
                    }
                    if member["evaluation_status"] == "pending":
                        destination = HERE / "baselines" / f"{member['inventory_label']}.json"
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        destination.write_text(json.dumps(doc, indent=2) + "\n")
                        if row["baseline_status"] == "compatible":
                            source = inputs.load(member["session_id"])
                            assert source.input_manifest_sha256 == doc["input_manifest_sha256"]
                            assert (
                                source.analysis_manifest_sha256 == doc["analysis_manifest_sha256"]
                            )
                            row["input_status"] = "tracking_source_loaded_and_bound"
                else:
                    row["input_status"] = "requires_baseline_or_source_preparation"
            except (OSError, ValueError, KeyError) as error:
                row["error"] = repr(error)
                row["input_status"] = "failed"
            rows.append(row)
            if member["evaluation_status"] == "pending":
                print(
                    member["inventory_label"],
                    row["baseline_status"],
                    row["input_status"],
                    row.get("error", ""),
                    flush=True,
                )
    finally:
        inputs.close()
    output.write_text(
        json.dumps(
            dict(
                manifest_sha256=manifest_sha,
                seal_files_verified=len(seal["files"]),
                expected_configuration=expected_config,
                members=rows,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
