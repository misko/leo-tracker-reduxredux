"""Version-one ALGO07v5 evidence with explicit initial-control reuse."""

from leo.contracts import localization_v3, localization_v4
from leo.contracts._localization_native import validate_native_provenance
from leo.contracts.localization_v3 import validate_identity as validate_identity

MODEL = "algo07v5-native-v1"
INITIAL_CONTROL_POLICY = "winner-arm-phase0-fit-v1"
ANNOTATION_TRAINING_POLICY = "lbfgsb-full5-625-v1"
ANNOTATION_FALLBACK_POLICY = "lbfgsb-gn-fallback-full5-v1"
INCLUSION_CONTROL_POLICY = "native-complete-controls-v1"
JOINT_SCHEDULE_POLICY = "defer-factorized-unless-retry-v1"
RECOVERY_TARGET_POLICY = "rf-target-prefix-v1"
INITIAL_DISCOVERY_POLICY = "initial-discovery-v1"
INITIAL_SEED_POLICIES = ("legacy", "anchor-round-robin-v1")
INITIAL_RANKING_POLICIES = ("legacy", "warm-center-v1")
DIRECT_GAP_POLICY = "direct-timing-gap-v1"


def direct_gap_policy(identifier=DIRECT_GAP_POLICY):
    if identifier != DIRECT_GAP_POLICY:
        raise ValueError("Unknown ALGO07v5 direct gap policy")
    return dict(
        id=DIRECT_GAP_POLICY, maximum_components=1, gap_s=5,
        minimum_points=12, minimum_span_s=10,
        selection="wholly unowned matched current-large proper timing components; "
                  "descending points then track and branch IDs",
        skipped_parent_prerequisites=["parent independent identity",
                                      "parent shared-family inclusion rejection"],
        independent_branch_identity_required=True, matched_c_arms=True, GPS_used=False,
    )


def validate_direct_gap_policy(value):
    expected = direct_gap_policy()
    if (type(value) is not dict or value.keys() != expected.keys()
            or any(type(value[key]) is not type(item) or value[key] != item
                   for key, item in expected.items())):
        raise ValueError("Complete ALGO07v5 direct gap policy required")
    return value


def validate_direct_gap_selection(gap, policy):
    validate_direct_gap_policy(policy)
    if (type(gap) is not dict or gap.get("policy") != policy
            or type(gap.get("targets")) is not list
            or len(gap["targets"]) > 1):
        raise ValueError("Direct gap selection must bind its policy and one-component limit")
    return gap


def initial_discovery_policy(seed_policy="legacy", ranking_policy="legacy"):
    if (type(seed_policy) is not str or seed_policy not in INITIAL_SEED_POLICIES
            or type(ranking_policy) is not str or ranking_policy not in INITIAL_RANKING_POLICIES):
        raise ValueError("Unknown ALGO07v5 initial discovery policy")
    return dict(id=INITIAL_DISCOVERY_POLICY, seed_policy=seed_policy,
                ranking_policy=ranking_policy)


def validate_initial_discovery_policy(value):
    if (type(value) is not dict
            or set(value) != {"id", "seed_policy", "ranking_policy"}
            or value != initial_discovery_policy(value["seed_policy"], value["ranking_policy"])):
        raise ValueError("Complete ALGO07v5 initial discovery policy required")
    return value


def validate_initial_discovery_selection(initial, policy):
    validate_initial_discovery_policy(policy)
    if (type(initial) is not dict
            or initial.get("initial_discovery_policy") != policy):
        raise ValueError("Initial discovery selection must bind its policy")
    validate_initial_discovery_policy(initial["initial_discovery_policy"])
    return initial


def recovery_target_policy(limit):
    if type(limit) is not int or not 0 <= limit <= 8:
        raise ValueError('Recovery target limit must be an integer in 0..8')
    return dict(id=RECOVERY_TARGET_POLICY, maximum_targets=limit, original_maximum_targets=8,
                order='descending observation count then track id',
                scope='predictive prefix; numerical replay of completed prefix',
                per_target_fit_and_audit_budget='unchanged', GPS_used=False)


def validate_recovery_target_policy(value):
    if type(value) is not dict or 'maximum_targets' not in value:
        raise ValueError('Complete recovery target policy required')
    expected = recovery_target_policy(value['maximum_targets'])
    if value.keys() != expected.keys() or any(
            type(value[k]) is not type(v) or value[k] != v for k, v in expected.items()):
        raise ValueError('Complete recovery target policy required')
    return value


def validate_target_selection(inventory, policy):
    validate_recovery_target_policy(policy)
    if (type(inventory) is not dict or type(inventory.get('target_limit')) is not int
            or inventory['target_limit'] != policy['maximum_targets']):
        raise ValueError('Recovery target selection must bind its limit')
    original = inventory.get('original_selected_track_ids')
    selected = inventory.get('selected_targets')
    omitted = inventory.get('policy_omitted_track_ids')
    if (type(original) is not list or len(original) > 8
            or any(type(tid) is not str or not tid for tid in original)
            or len(set(original)) != len(original)
            or type(selected) is not list
            or any(type(row) is not dict or type(row.get('track_id')) is not str
                   for row in selected)
            or type(omitted) is not list
            or [r['track_id'] for r in selected] != original[:policy['maximum_targets']]
            or omitted != original[policy['maximum_targets']:]):
        raise ValueError('Recovery target selection must retain its ordered prefix and omissions')
    return inventory


def joint_schedule_policy(identifier=JOINT_SCHEDULE_POLICY):
    if identifier != JOINT_SCHEDULE_POLICY:
        raise ValueError('Unknown ALGO07v5 joint schedule policy')
    return dict(id=identifier, scope='one paired joint experiment',
                order=['control', 'joint', 'factorized'],
                omit_factorized='joint accepted or control/joint audits rule out numerical retry',
                optimizer_and_phase_budgets='unchanged',
                bound='request-bound native manifest',
                unknown_callbacks='original schedule',
                numerical_policy='known original NumericalPolicy only')


def validate_joint_schedule_policy(value):
    if type(value) is not dict or value != joint_schedule_policy():
        raise ValueError('Complete ALGO07v5 joint schedule policy required')
    return value


def joint_schedule_counts(rows):
    return dict(started=len(rows), completed=sum(r['state'] == 'completed' for r in rows),
                failed=sum(r['state'] == 'failed' for r in rows),
                in_progress=sum(r['state'] == 'started' for r in rows),
                ineligible=sum(not r['eligible'] for r in rows),
                **{'factorized_' + status: sum(r['factorized'] == status for r in rows)
                   for status in ('computed', 'omitted', 'incomplete', 'not_reached')})


def validate_joint_schedule_work(value, policy, binding):
    validate_joint_schedule_policy(policy)
    if (type(value) is not dict
            or set(value) != {'schema_version', 'policy', 'backend_manifest_sha256',
                              'experiments', 'counts'}
            or type(value['schema_version']) is not int or value['schema_version'] != 1
            or value['policy'] != policy or value['backend_manifest_sha256'] != binding
            or type(value['experiments']) is not list):
        raise ValueError('Bound joint schedule work required')
    validate_joint_schedule_policy(value['policy'])
    for row in value['experiments']:
        if (type(row) is not dict
                or set(row) != {'optimizer', 'eligible', 'state', 'factorized',
                                'reason', 'completed_arms'}
                or row['optimizer'] not in ('lbfgsb', 'powell')
                or type(row['eligible']) is not bool
                or row['state'] not in ('started', 'completed', 'failed')
                or row['factorized'] not in ('computed', 'omitted', 'incomplete', 'not_reached')
                or type(row['completed_arms']) is not int
                or not 0 <= row['completed_arms'] <= 2
                or (row['factorized'] == 'computed') != (row['completed_arms'] == 2)
                or (row['factorized'] in ('omitted', 'not_reached') and row['completed_arms'])
                or (row['factorized'] == 'omitted' and not row['eligible'])
                or (row['factorized'] == 'omitted') != (row['reason'] in (
                    'joint_already_qualified', 'numerical_retry_ruled_out'))
                or (row['factorized'] != 'omitted' and row['reason'] is not None)
                or (row['state'] == 'completed'
                    and row['factorized'] not in ('computed', 'omitted'))):
            raise ValueError('Consistent actual joint experiment states required')
    counts = value['counts']
    if (type(counts) is not dict or counts != joint_schedule_counts(value['experiments'])
            or any(type(n) is not int or n < 0 for n in counts.values())):
        raise ValueError('Joint schedule aggregate differs from experiments')
    return value


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
    initial = evidence["audit"].get("initial")
    if "initial_discovery_policy" in evidence["provenance"]:
        validate_initial_discovery_selection(initial,
            evidence["provenance"]["initial_discovery_policy"])
    elif isinstance(initial, dict) and "initial_discovery_policy" in initial:
        raise ValueError("Initial discovery selection requires its explicit policy")
    if "annotation_training_policy" in evidence["provenance"]:
        validate_annotation_training_policy(evidence["provenance"]["annotation_training_policy"])
    if "inclusion_control_policy" in evidence["provenance"]:
        provenance = evidence["provenance"]
        validate_inclusion_control_work(provenance.get("inclusion_control_work"),
                                        provenance["inclusion_control_policy"],
                                        provenance["native_backend"]["manifest_sha256"])
    elif 'inclusion_control_work' in evidence['provenance']:
        raise ValueError('Inclusion control work requires its explicit policy')
    if 'joint_schedule_policy' in evidence['provenance']:
        provenance = evidence['provenance']
        validate_joint_schedule_work(provenance.get('joint_schedule_work'),
                                     provenance['joint_schedule_policy'],
                                     provenance['native_backend']['manifest_sha256'])
    elif 'joint_schedule_work' in evidence['provenance']:
        raise ValueError('Joint schedule work requires its explicit policy')
    inventory = evidence['audit'].get('recovery_inventory')
    if 'recovery_target_policy' in evidence['provenance']:
        validate_target_selection(inventory, evidence['provenance']['recovery_target_policy'])
    elif isinstance(inventory, dict) and 'target_limit' in inventory:
        raise ValueError('Recovery target selection requires its explicit policy')
    gap = evidence['audit'].get('gap_recovery')
    if 'direct_gap_policy' in evidence['provenance']:
        validate_direct_gap_selection(gap, evidence['provenance']['direct_gap_policy'])
        if evidence['provenance'].get('recovery_target_policy') != recovery_target_policy(0):
            raise ValueError('Direct gap policy requires explicit zero recovery targets')
    elif isinstance(gap, dict) and 'policy' in gap:
        raise ValueError('Direct gap selection requires its explicit policy')
    return evidence


def validate(receipt):
    return localization_v3._validate(receipt, MODEL)
