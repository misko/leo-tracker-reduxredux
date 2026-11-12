"""Version-one ALGO07v5 evidence with explicit initial-control reuse."""

from leo.contracts import localization_v3, localization_v4
from leo.contracts._localization_native import validate_native_provenance
from leo.contracts.localization_v3 import validate_identity as validate_identity

MODEL = "algo07v5-native-v1"
INITIAL_CONTROL_POLICY = "winner-arm-phase0-fit-v1"
ANNOTATION_TRAINING_POLICY = "lbfgsb-full5-625-v1"
ANNOTATION_FALLBACK_POLICY = "lbfgsb-gn-fallback-full5-v1"
INCLUSION_CONTROL_POLICY = "native-complete-controls-v1"


def inclusion_control_policy(identifier=INCLUSION_CONTROL_POLICY):
    """Describe exact per-invocation control reuse without reducing scientific work budgets."""
    if identifier != INCLUSION_CONTROL_POLICY:
        raise ValueError("Unknown ALGO07v5 inclusion control policy")
    return dict(id=identifier, scope="one recovery invocation",
                scan="all fields including geometry",
                normalized_lists=["tracks", "white", "rx_basis"],
                count="original graph count",
                context=["node", "keep", "powers", "means", "model", "entries"],
                inventory="policy", bound="request-bound native manifest",
                values="deepcopy on store and hit", unknown_callbacks="ineligible",
                numerical_policy="ineligible", conditional_satellite_refresh="ineligible")


def validate_inclusion_control_policy(value):
    if value != inclusion_control_policy() or type(value) is not dict:
        raise ValueError("Complete ALGO07v5 inclusion control policy required")
    return value


def validate_inclusion_control_work(value, policy, binding):
    validate_inclusion_control_policy(policy)
    if (type(value) is not dict
            or set(value) != {"schema_version", "policy", "backend_manifest_sha256",
                              "invocations", "counts"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["policy"] != policy or value["backend_manifest_sha256"] != binding
            or type(value["invocations"]) is not list):
        raise ValueError("Bound inclusion control work required")
    validate_inclusion_control_policy(value["policy"])
    keys = {"requests", "computed", "reused", "failed", "unkeyable", "in_progress"}
    for counts in [*value["invocations"], value["counts"]]:
        if (type(counts) is not dict or set(counts) != keys
                or any(type(n) is not int or n < 0 for n in counts.values())
                or counts["requests"] != sum(counts[k] for k in
                                            ("computed", "reused", "failed", "in_progress"))
                or counts["unkeyable"] > counts["requests"] - counts["reused"]):
            raise ValueError("Consistent integer inclusion control counts required")
    if value["counts"] != {key: sum(row[key] for row in value["invocations"]) for key in keys}:
        raise ValueError("Inclusion control aggregate differs from invocations")
    return value


def annotation_training_policy(identifier=ANNOTATION_TRAINING_POLICY):
    """Return an independent, complete descriptor of the opt-in training budget."""
    if identifier == ANNOTATION_FALLBACK_POLICY:
        return dict(
            id=identifier, optimizer="lbfgsb_with_reference_gn_fallback",
            phase_rounds=5, position_steps=48,
            primary=annotation_training_policy(),
            fallback=dict(optimizer="original_gn", iterations=48,
                          residual_call_cap=625, start="original phase start",
                          trigger="primary not converged"),
            total_residual_call_cap=1250,
            history_kind="all physical residual evaluations across attempts",
        )
    if identifier != ANNOTATION_TRAINING_POLICY:
        raise ValueError("Unknown ALGO07v5 annotation training policy")
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

    if (not isinstance(value, dict)
            or value.get("id") not in (ANNOTATION_TRAINING_POLICY, ANNOTATION_FALLBACK_POLICY)
            or not matches(value, annotation_training_policy(value["id"]))):
        raise ValueError("Complete ALGO07v5 annotation training policy required")
    return value


def validate_evidence(evidence):
    localization_v3._validate_evidence(evidence, MODEL)
    validate_native_provenance(evidence, MODEL, localization_v4.MODEL)
    if evidence["provenance"].get("initial_control_policy") != INITIAL_CONTROL_POLICY:
        raise ValueError("ALGO07v5 initial control policy binding required")
    if "annotation_training_policy" in evidence["provenance"]:
        validate_annotation_training_policy(evidence["provenance"]["annotation_training_policy"])
    if "inclusion_control_policy" in evidence["provenance"]:
        provenance = evidence["provenance"]
        validate_inclusion_control_work(provenance.get("inclusion_control_work"),
                                        provenance["inclusion_control_policy"],
                                        provenance["native_backend"]["manifest_sha256"])
    elif 'inclusion_control_work' in evidence['provenance']:
        raise ValueError('Inclusion control work requires its explicit policy')
    return evidence


def validate(receipt):
    return localization_v3._validate(receipt, MODEL)
