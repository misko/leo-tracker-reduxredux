import pytest
from pydantic import ValidationError

from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position_v2 import RegionalPositionDocumentV2
from tests.contracts.test_regional_position_products import document as legacy_document


def document():
    payload = legacy_document().model_dump(mode="json")
    payload.update(schema_version=2, analysis_id="scanner-regional-position-v2")
    payload["methods"] = payload["methods"][1:]
    payload["configuration"] = configuration()
    payload["configuration_sha256"] = canonical_digest(payload["configuration"])
    return RegionalPositionDocumentV2.model_validate(payload)


def test_v2_roundtrips_and_v1_stays_a_two_method_contract():
    doc = document()
    assert RegionalPositionDocumentV2.model_validate_json(doc.model_dump_json()) == doc
    assert [m.name for m in legacy_document().methods] == ["T1AT", "V16"]


@pytest.mark.parametrize("mutation", ["method", "arm", "protocol", "digest", "truth"])
def test_hard60_contract_rejects_incompatible_evidence(mutation):
    payload = document().model_dump(mode="json")
    if mutation == "method":
        payload["methods"][0]["name"] = "T1AT"
    elif mutation == "arm":
        payload["methods"][0]["arms"].pop()
    elif mutation == "protocol":
        payload["configuration"]["protocol"] = "legacy"
        payload["configuration_sha256"] = canonical_digest(payload["configuration"])
    elif mutation == "digest":
        payload["configuration"]["other"] = "changed"
    else:
        payload["known_position_used_for_inference"] = True
    with pytest.raises(ValidationError):
        RegionalPositionDocumentV2.model_validate(payload)
