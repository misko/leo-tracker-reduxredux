"""Version-one ALGO07v5 evidence with explicit initial-control reuse."""

from leo.contracts import localization_v3, localization_v4
from leo.contracts._localization_native import validate_native_provenance
from leo.contracts.localization_v3 import validate_identity as validate_identity

MODEL = "algo07v5-native-v1"
INITIAL_CONTROL_POLICY = "winner-arm-phase0-fit-v1"
ANNOTATION_TRAINING_POLICY = "lbfgsb-full5-625-v1"


def annotation_training_policy():
    """Return an independent, complete descriptor of the opt-in training budget."""
    return dict(
        id=ANNOTATION_TRAINING_POLICY,
        optimizer="lbfgsb", method="L-BFGS-B",
        options=dict(maxiter=48, maxfun=625, eps=0.001,
                     ftol=2.220446049250313e-9, gtol=1e-5, maxls=20, maxcor=10),
        residual_call_cap=625, phase_rounds=5, position_steps=48,
        history_kind="all residual evaluations including Jacobians",
    )


def validate_annotation_training_policy(value):
    def matches(actual, expected):
        if type(actual) is not type(expected):
            return False
        if isinstance(expected, dict):
            return actual.keys() == expected.keys() and all(
                matches(actual[key], item) for key, item in expected.items()
            )
        return actual == expected

    if not matches(value, annotation_training_policy()):
        raise ValueError("Complete ALGO07v5 annotation training policy required")
    return value


def validate_evidence(evidence):
    localization_v3._validate_evidence(evidence, MODEL)
    validate_native_provenance(evidence, MODEL, localization_v4.MODEL)
    if evidence["provenance"].get("initial_control_policy") != INITIAL_CONTROL_POLICY:
        raise ValueError("ALGO07v5 initial control policy binding required")
    if "annotation_training_policy" in evidence["provenance"]:
        validate_annotation_training_policy(evidence["provenance"]["annotation_training_policy"])
    return evidence


def validate(receipt):
    return localization_v3._validate(receipt, MODEL)
