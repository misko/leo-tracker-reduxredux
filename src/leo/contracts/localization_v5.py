"""Version-one ALGO07v5 evidence with explicit initial-control reuse."""

from leo.contracts import localization_v3, localization_v4
from leo.contracts._localization_native import validate_native_provenance
from leo.contracts.localization_v3 import validate_identity as validate_identity

MODEL = "algo07v5-native-v1"
INITIAL_CONTROL_POLICY = "winner-arm-phase0-fit-v1"


def validate_evidence(evidence):
    localization_v3._validate_evidence(evidence, MODEL)
    validate_native_provenance(evidence, MODEL, localization_v4.MODEL)
    if evidence["provenance"].get("initial_control_policy") != INITIAL_CONTROL_POLICY:
        raise ValueError("ALGO07v5 initial control policy binding required")
    return evidence


def validate(receipt):
    return localization_v3._validate(receipt, MODEL)
