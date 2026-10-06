import pytest
from pydantic import ValidationError

from leo.contracts.adaptive_tle_position import (
    AdaptiveTleAccountingV1,
    AdaptiveTleCandidateV1,
    AdaptiveTlePositionDocumentV1,
    AdaptiveTlePositionDocumentV2,
    AdaptiveTlePriorResultV1,
    AdaptiveTlePriorResultV2,
    AdaptiveTleRegionV1,
    AdaptiveTleRegionV2,
)

DIGEST = "sha256:" + "1" * 64


def candidate():
    return AdaptiveTleCandidateV1(
        latitude_deg=38,
        longitude_deg=-122,
        east_km=1,
        north_km=2,
        spacing_km=12.5,
        capped_weighted_rmse_hz=185,
        matched_track_count=32,
        unmatched_track_count=2,
        qualifying_observation_count=720,
    )


def prior(name):
    return AdaptiveTlePriorResultV1(
        name=name,
        region=AdaptiveTleRegionV1(center_latitude_deg=38, center_longitude_deg=-122),
        search_complete=False,
        stop_reason="budget-exhausted",
        accounting=AdaptiveTleAccountingV1(
            reconstructed_track_count=34,
            eligible_track_count=34,
            eligible_observation_count=750,
            evaluated_point_count=400,
            finest_evaluated_point_count=200,
            deferred_cell_count=50,
            runtime_ms=45_000,
        ),
        selected=candidate(),
        finest=candidate(),
    )


def document():
    return AdaptiveTlePositionDocumentV1(
        session_id="scan-1",
        input_manifest_sha256=DIGEST,
        analysis_manifest_sha256=DIGEST,
        configuration_sha256=DIGEST,
        evidence_sha256=DIGEST,
        state="diagnostic",
        priors=(prior("sacramento"), prior("reno")),
    )


def document_v2():
    def value(name, radius):
        legacy = prior(name)
        return AdaptiveTlePriorResultV2(
            **legacy.model_dump(exclude={"region"}),
            region=AdaptiveTleRegionV2(
                center_latitude_deg=38,
                center_longitude_deg=-122,
                radius_km=radius,
            ),
        )

    return AdaptiveTlePositionDocumentV2(
        session_id="scan-1",
        input_manifest_sha256=DIGEST,
        analysis_manifest_sha256=DIGEST,
        configuration_sha256=DIGEST,
        evidence_sha256=DIGEST,
        state="diagnostic",
        priors=(value("sacramento", 250), value("reno", 500)),
    )


def document_v3():
    from leo.contracts.adaptive_tle_position import AdaptiveTlePositionDocumentV3

    payload = document_v2().model_dump()
    payload.update(schema_version=3, analysis_id="scanner-adaptive-tle-position-v3")
    payload["priors"] = payload["priors"][:1]
    for name in ("selected", "finest"):
        payload["priors"][0][name]["horizontal_error_m"] = 1234.0
    return AdaptiveTlePositionDocumentV3.model_validate(payload)


def test_v3_is_sacramento_only_without_weakening_v2():
    from leo.contracts.adaptive_tle_position import AdaptiveTlePositionDocumentV3

    assert len(document_v3().priors) == 1
    payload = document_v3().model_dump()
    payload["priors"][0]["name"] = "reno"
    with pytest.raises(ValidationError, match="prior inventory"):
        AdaptiveTlePositionDocumentV3.model_validate(payload)
    with pytest.raises(ValidationError, match="prior inventory"):
        AdaptiveTlePositionDocumentV2.model_validate(
            {**document_v2().model_dump(), "priors": document_v3().model_dump()["priors"]}
        )
    payload = document_v3().model_dump()
    payload["priors"][0]["selected"]["horizontal_error_m"] = None
    with pytest.raises(ValidationError, match="require reference error"):
        AdaptiveTlePositionDocumentV3.model_validate(payload)


def test_contract_requires_canonical_two_prior_inventory():
    assert [item.name for item in document().priors] == ["sacramento", "reno"]
    with pytest.raises(ValidationError, match="prior inventory"):
        AdaptiveTlePositionDocumentV1.model_validate(
            {**document().model_dump(), "priors": [prior("reno").model_dump()]}
        )


def test_contract_labels_selection_and_disclaims_fix():
    value = document()
    assert value.identity_selection == "randomized-evaluation-rms-v1"
    assert value.known_position_used_for_inference is False
    assert value.position_fix_claimed is False


def test_contract_rejects_unexplained_failure_and_nonfinite_diagnostics():
    payload = document().model_dump()
    payload.update(state="failed", priors=[])
    with pytest.raises(ValidationError, match="requires a reason"):
        AdaptiveTlePositionDocumentV1.model_validate(payload)
    payload.update(reasons=["numerical-failure"], diagnostics={"bad": float("nan")})
    with pytest.raises(ValidationError, match="must be finite"):
        AdaptiveTlePositionDocumentV1.model_validate(payload)


def test_contract_requires_candidates_for_each_diagnostic_prior():
    payload = document().model_dump()
    payload["priors"][0]["selected"] = None
    with pytest.raises(ValidationError, match="requires a selected"):
        AdaptiveTlePositionDocumentV1.model_validate(payload)


def test_v2_contract_requires_250km_sacramento_and_500km_reno():
    assert [item.region.radius_km for item in document_v2().priors] == [250, 500]
    payload = document_v2().model_dump()
    payload["priors"][0]["region"]["radius_km"] = 500
    with pytest.raises(ValidationError, match="v2 prior radii"):
        AdaptiveTlePositionDocumentV2.model_validate(payload)


def test_v2_contract_rejects_nonfinite_nested_diagnostics():
    payload = document_v2().model_dump()
    payload["diagnostics"] = {"nested": [{"score": float("inf")}]}
    with pytest.raises(ValidationError, match="must be finite"):
        AdaptiveTlePositionDocumentV2.model_validate(payload)
