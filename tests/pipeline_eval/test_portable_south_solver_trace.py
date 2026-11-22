from hashlib import sha256
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[2] / "reports/ALGO08/single-core-2x/portable_south_solver_trace.py"
TRACE = runpy.run_path(str(SOURCE))


def test_trace_keeps_track_identity_and_uses_the_actual_mixed_fragment_mask():
    scan = SimpleNamespace(tracks=[dict(key="b", observation_ids=["4", "5"], receiver=2, channel=1),
                                   dict(key="a", observation_ids=["1", "2", "3"], receiver=1, channel=2)])
    rows = [dict(component="b", active_curvature=True, candidate_norad=2800),
            dict(component="a", active_curvature=True, candidate_norad=4000)]
    node = dict(seed=dict(rows=rows), aliases=[-1, 2])
    kept = TRACE["identity"](scan, node, [False, True, True, False, True])
    assert kept == [
        dict(component="a", norad=4000, alias=2, receiver=1, channel=2, points=2,
             observations=sha256(b"1\n3").hexdigest()),
        dict(component="b", norad=2800, alias=-1, receiver=2, channel=1, points=1,
             observations=sha256(b"5").hexdigest()),
    ]
    with pytest.raises(ValueError):
        TRACE["identity"](scan, node, [True] * 6)


def test_owner_delta_separates_satellite_changes_from_support_and_role():
    original = {"stay": ["t1", 1, "conditional"], "retire": ["t2", 1, "conditional"],
                "role": ["t2", 1, "conditional"], "relabel": ["t3", 3, "conditional"]}
    candidate = {"stay": ["t1", 1, "conditional"], "join": ["t2", 1, "linear_predictive"],
                 "role": ["t2", 1, "linear_predictive"], "relabel": ["t3", 4, "conditional"]}
    assert TRACE["owner_audit"](original, candidate) == dict(
        common=3, unchanged=1, satellite_changes=1, changed_owner_or_role=2,
        installed_only=[["t2", 1, "conditional", 1]],
        covariance_only=[["t2", 1, "linear_predictive", 1]],
        other_common_changes=[["t2", 1, "linear_predictive", 1], ["t3", 4, "conditional", 1]],
    )
