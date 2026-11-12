"""Version-one native ALGO07v4 scientific evidence and receipt."""

from leo.contracts import localization_v3
from leo.contracts._localization_native import validate_native_provenance
from leo.contracts.localization_v3 import validate_identity as validate_identity

MODEL = "algo07v4-native-v1"


def validate_evidence(evidence):
    localization_v3._validate_evidence(evidence, MODEL)
    return validate_native_provenance(evidence, MODEL, MODEL)


def validate(receipt):
    return localization_v3._validate(receipt, MODEL)
