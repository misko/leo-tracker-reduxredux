from copy import deepcopy

import pytest

from leo.contracts.fast_standard_analysis import MODEL as POLICY_MODEL
from leo.contracts.localization_v3 import MODEL, validate, validate_evidence, validate_identity
from tests.localization_v3_fixture import evidence_fixture


def receipt():
    evidence, _ = evidence_fixture()
    return dict(
        schema_version=1,
        model_version=MODEL,
        policy_model_version=POLICY_MODEL,
        state="complete",
        **evidence["identity"],
        result_sha256="sha256:" + "0" * 64,
        result_bytes=100,
        glrt_points=2,
        arms=evidence["presentation"]["arms"],
    )


@pytest.mark.parametrize(
    "key,value",
    [
        ("model_version", POLICY_MODEL),
        ("schema_version", 2),
        ("state", "partial"),
        ("result_sha256", "../file"),
        ("result_bytes", 0),
        ("result_bytes", True),
        ("glrt_points", False),
        ("input_sha256", "missing"),
        ("session_id", "../escape"),
    ],
)
def test_receipt_requires_own_version_complete_state_and_content_bindings(key, value):
    document = receipt()
    assert validate(document) is document
    document[key] = value
    with pytest.raises(ValueError):
        validate(document)


def test_receipt_requires_both_arms_and_finite_physical_positions():
    original = receipt()
    for mutate in (
        lambda d: d["arms"].pop("c0"),
        lambda d: d["arms"]["c0"].update(endpoint_latlon=[float("nan"), -122.0]),
        lambda d: d["arms"]["c0"].update(endpoint_latlon=[100.0, -122.0]),
        lambda d: d["arms"]["c0"].update(associated_points=3),
        lambda d: d["arms"]["c0"].update(owner_sha256="sha256:stale"),
    ):
        changed = deepcopy(original)
        mutate(changed)
        with pytest.raises(ValueError):
            validate(changed)


def test_evaluation_reference_is_not_an_identity_or_inference_input():
    evidence, _ = evidence_fixture()
    identity = dict(evidence["identity"], evaluation_reference=[37.0, -122.0])
    with pytest.raises(ValueError):
        validate_identity(identity)
    evidence["render"]["reference_usage"] = "fit_prior"
    with pytest.raises(ValueError, match="presentation-only"):
        validate_evidence(evidence)
