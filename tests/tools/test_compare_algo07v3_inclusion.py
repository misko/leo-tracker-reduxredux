from copy import deepcopy

import pytest
from compare_algo07v3_inclusion import compare


def test_comparison_requires_retry_science_and_unchanged_prefix():
    prefix = dict(recovery_inventory=dict(owners={"native": 123}))
    reference = dict(
        predictive_annotation=dict(folds=[1, 2, 3]),
        predictive_inclusion=dict(
            status="qualified_candidate", retry=dict(objective="0x1.0000000000000p+0")
        ),
    )
    candidate = dict(prefix, **deepcopy(reference))
    assert compare(reference, candidate, prefix)["exact"]
    candidate["predictive_inclusion"]["retry"]["objective"] = "0x1.0000000000001p+0"
    with pytest.raises(ValueError, match="retry.objective"):
        compare(reference, candidate, prefix)
    candidate = dict(prefix, **deepcopy(reference))
    candidate["recovery_inventory"] = dict(owners={"native": 124})
    with pytest.raises(ValueError, match="Preceding scientific prefix"):
        compare(reference, candidate, prefix)


def test_comparison_does_not_accept_a_reference_missing_annotation():
    with pytest.raises(ValueError, match="Incomplete external reference"):
        compare(dict(predictive_inclusion={}), {}, {})
