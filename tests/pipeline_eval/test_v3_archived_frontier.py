from copy import deepcopy

import pytest

from reports.ALGO08.v3 import archived_frontier as frontier


def fixture_pair():
    case = dict(case="recording-A", raw_authority="raw", session="session", region={"radius_km": 25})
    spec = {"build": "A"}
    run = dict(raw_authority="raw", artifacts=[dict(name=name) for name in frontier.PLOTS],
               receipt=dict(session_id="session", region=case["region"], window_count=3, decision="complete"),
               scientific_digests=dict(path="path-pin", grid="grid-pin"))
    pair = dict(cpu=2, archive="archive", recording="recording-A", runs={"candidate": run},
                candidate_specification=spec, candidate_specification_digest=frontier.canonical_digest(spec))
    return case, pair


def test_comparable_publication():
    case, pair = fixture_pair()
    assert frontier.matched(deepcopy(pair), pair, case) == pair["runs"]["candidate"]


@pytest.mark.parametrize("change", ["archive", "cpu", "raw_authority", "region", "figure", "pin"])
def test_mismatched_receipts_are_rejected(change):
    case, reference = fixture_pair()
    pair = deepcopy(reference)
    run = pair["runs"]["candidate"]
    if change in ("archive", "cpu"):
        pair[change] = "other"
    elif change == "raw_authority":
        run[change] = "other"
    elif change == "region":
        run["receipt"][change] = {"radius_km": 50}
    elif change == "figure":
        run["artifacts"].pop()
    else:
        pair["candidate_specification"]["build"] = "B"
    with pytest.raises(ValueError):
        frontier.matched(pair, reference, case)
