import pytest
from retained_adapter import admitted_original, continue_branch


def test_admission_preserves_endpoint_and_rejects_wrong_geometry():
    seed = dict(satellite_indices=[1, 3], vector=[2.0, 4.0] + [0.0] * 7)
    fitted = dict(vector=seed["vector"], objective=10.0, converged=False)
    original = admitted_original([2.0, 4.0], seed, fitted, 5)
    seed["vector"][0] = 9.0
    assert original["bootstrap"]["vector"][0] == 2.0
    with pytest.raises(ValueError, match="position"):
        admitted_original([0.0, 4.0], original["bootstrap"], fitted, 5)
    with pytest.raises(ValueError, match="outside"):
        admitted_original([2.0, 4.0], original["bootstrap"], fitted, 3)


def test_three_regions_failures_preserved_and_both_arms_shared_joint():
    case = dict(observations="obs", bank="bank", prior="prior")
    triggers = [dict(key=str(i)) for i in range(3)]
    seen = []

    def recover(obs, bank, prior, trigger, stage):
        seen.append(trigger["key"])
        return dict(
            finals=[] if trigger["key"] == "1" else [trigger],
            recovery=dict(status="failed" if trigger["key"] == "1" else "qualified"),
        )

    def joint(obs, bank, prior, regions, stage):
        assert len(regions) == 3
        assert regions["retained-1"]["recovery"]["status"] == "failed"
        return {"zero-c": {}, "fitted-c": {}}, [], ["failure retained"]

    result = continue_branch(case, triggers, None, recover=recover, joint=joint)
    assert seen == ["0", "1", "2"]
    assert set(result["operational"]) == {"zero-c", "fitted-c"}
    with pytest.raises(ValueError, match="three"):
        continue_branch(case, triggers[:2], None, recover=recover, joint=joint)
