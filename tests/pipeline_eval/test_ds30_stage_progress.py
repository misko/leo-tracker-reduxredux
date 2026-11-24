from hashlib import sha256
import json

import pytest

from reports.ALGO08.v3 import ds30_stage_progress as stages


def snapshot(flags=(False, False), roles=("installed", "successor")):
    data = b"\n".join(json.dumps(dict(case="item", algorithm=role, verified_pair=flag)).encode()
                      for role, flag in zip(roles, flags, strict=True))
    return data, dict(plan_sha256=stages.PLAN, combined_sha256="sha256:" + sha256(data).hexdigest(),
                      proofs={}, pending_relocation_cases=sorted(stages.RELOCATED))


def test_unstarted_stage_is_unmeasured_and_snapshot_bytes_are_bound():
    raw, seal = snapshot()
    assert stages.verified_measurements(raw, seal, {"item": {}}) == []
    with pytest.raises(ValueError, match="Export and seal"):
        stages.verified_measurements(raw + b"\n", seal, {"item": {}})


@pytest.mark.parametrize("flags,roles,reason", [
    ((True, False), ("installed", "successor"), "same verified pair"),
    ((False, False), ("installed", "installed"), "Duplicate"),
    ((False,), ("successor",), "both arms"),
])
def test_missing_duplicated_and_partly_verified_pairs_raise(flags, roles, reason):
    raw, seal = snapshot(flags, roles)
    with pytest.raises(ValueError, match=reason):
        stages.verified_measurements(raw, seal, {"item": {}})


def test_relocation_roster_must_be_partitioned_by_its_signed_proofs():
    raw, seal = snapshot()
    seal["pending_relocation_cases"] = []
    with pytest.raises(ValueError, match="relocation proof roster"):
        stages.verified_measurements(raw, seal, {"item": {}})
