from __future__ import annotations

import hashlib
import json

from audit_soft_geometry import RECEIPT, SCHEMA, digest, receipt, verify_sources


def test_receipt_is_json_safe_and_does_not_name_reference_inputs():
    encoded = json.dumps(receipt(), allow_nan=False)
    assert RECEIPT["schema"] == SCHEMA
    assert "evaluation.json" not in encoded
    assert "reference_site" not in encoded
    assert RECEIPT["scope"]["reference_or_evaluation_read"] is False
    assert RECEIPT["scope"]["fits_run"] is False


def test_receipt_records_fixed_soft_model_and_scan_identity():
    definitions = RECEIPT["definitions"]
    assert definitions["sigma_hz"] == 200.0
    assert definitions["timing_finite_difference_steps_s"] == [1e-4, 1e-3, 1e-2]
    assert definitions["position_finite_difference_step_km"] == 1e-3
    assert definitions["objective_scaled_coordinate_step"] == 1e-6
    assert {
        session: values["selected_satellites"]
        for session, values in RECEIPT["scans"].items()
    } == {
        "scan-fw-911c4e5db9243281": 13,
        "scan-fw-ffa1cc19d8d7c09f": 15,
    }


def test_receipt_copy_cannot_mutate_frozen_values():
    copied = receipt()
    copied["scans"]["scan-fw-911c4e5db9243281"]["family_rows"] = 0
    assert RECEIPT["scans"]["scan-fw-911c4e5db9243281"]["family_rows"] == 7404


def test_digest_and_source_verification_report_corruption(tmp_path):
    relative = next(iter(RECEIPT["source_hashes"]))
    target = tmp_path / relative
    target.parent.mkdir(parents=True)
    target.write_bytes(b"corrupt")
    assert digest(target) == hashlib.sha256(b"corrupt").hexdigest()
    verification = verify_sources(tmp_path)
    assert verification["available"] is False
    assert verification["mismatches"][relative]["actual"] == digest(target)
