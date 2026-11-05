import hashlib
from copy import deepcopy

import pytest
from compare_algo07v3_joint import compare, flag


def experiment():
    row = dict(
        result=dict(history=[dict(success=True)]),
        audit=dict(
            incumbent_owner_changes=[],
            phase_check=dict(phase_change_s=dict(hex=(0.001).hex())),
            exact_incumbent_orbits=[dict(all_pass=True)],
            checks=dict(incumbent_and_numerical=True, target_gates=True),
            RF_qualified_arm=True,
        ),
    )
    return dict(
        geometry={},
        records={
            m + "-" + a: deepcopy(row)
            for m in ("control", "factorized", "joint")
            for a in ("c0", "fitted_c")
        },
    )


def test_exact_joint_comparison_requires_every_arm_and_diagnostic():
    reference = experiment()
    assert compare(reference, deepcopy(reference))["control_and_joint_pass"]
    changed = deepcopy(reference)
    changed["records"]["factorized-c0"]["audit"]["checks"]["target_gates"] = False
    with pytest.raises(ValueError, match="Joint scientific"):
        compare(reference, changed)
    reference["records"].pop("factorized-fitted_c")
    with pytest.raises(ValueError, match="Complete six-fit"):
        compare(reference, reference)


def test_hashed_boolean_is_checked_not_treated_as_a_truthy_dictionary():
    value = dict(dtype="|b1", shape=[], sha256=hashlib.sha256(b"\x00").hexdigest())
    assert flag(value) is False
    value["sha256"] = "invalid"
    with pytest.raises(ValueError, match="fingerprinted boolean"):
        flag(value)
