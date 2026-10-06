import pytest
from pydantic import ValidationError

from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position_products import (
    RegionalPositionDocumentV1,
    RegionalPositionManifestV1,
    RegionalSearchPointV1,
)

DIGEST = "sha256:" + "1" * 64


def document():
    return RegionalPositionDocumentV1(
        session_id="scan-1",
        input_manifest_sha256=DIGEST,
        analysis_manifest_sha256=DIGEST,
        evidence_sha256=DIGEST,
        configuration={"prior": "sacramento"},
        configuration_sha256=canonical_digest({"prior": "sacramento"}),
        windows=0,
        reference_latitude_deg=37.849,
        reference_longitude_deg=-122.486,
        reference_evidence="evaluation fixture only",
        methods=[
            dict(
                name=name,
                state="insufficient",
                search_stop_reason="no-windows",
                arms=[dict(name=arm, reasons=["no-windows"]) for arm in ("fitted-c", "zero-c")],
            )
            for name in ("T1AT", "V16")
        ],
    )


def test_diagnostic_document_roundtrip():
    original = document()
    assert RegionalPositionDocumentV1.model_validate_json(original.model_dump_json()) == original


@pytest.mark.parametrize("mutation", ["missing-method", "missing-arm", "config", "nan", "truth"])
def test_document_rejects_incoherent_products(mutation):
    payload = document().model_dump(mode="json")
    if mutation == "missing-method":
        payload["methods"].pop()
    elif mutation == "missing-arm":
        payload["methods"][0]["arms"].pop()
    elif mutation == "config":
        payload["configuration"]["prior"] = "roof"
    elif mutation == "nan":
        payload["diagnostics"] = {"nested": [float("nan")]}
    else:
        payload["known_position_used_for_inference"] = True
    with pytest.raises(ValidationError):
        RegionalPositionDocumentV1.model_validate(payload)


def test_manifest_requires_correct_document_digest_and_two_artifacts():
    payload = dict(
        document=document(),
        document_sha256=DIGEST,
        artifacts=[dict(name=name, sha256=DIGEST, byte_count=20) for name in ("T1AT", "V16")],
    )
    with pytest.raises(ValidationError, match="document digest"):
        RegionalPositionManifestV1.model_validate(payload)
    payload["document_sha256"] = canonical_digest(document().model_dump(mode="json"))
    RegionalPositionManifestV1.model_validate(payload)
    payload["artifacts"].pop()
    with pytest.raises(ValidationError, match="PNG"):
        RegionalPositionManifestV1.model_validate(payload)


def test_missing_point_score_cannot_masquerade_as_convergence():
    with pytest.raises(ValidationError):
        RegionalSearchPointV1(east_km=0, north_km=0, spacing_km=100, converged=True)
