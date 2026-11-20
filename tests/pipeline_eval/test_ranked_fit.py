from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.ranked_fit_probe import outcomes
from tools.pipeline_eval.qualification.ranked_fit_trial import BEFORE, revised

MODE_SELECTION = """def vote(d, p, data, j):
    supported = j in p or data["held_owners"] >= 2
    if j in p:
        mode_bank = [-j]
{}
    return (j, tuple(mode_bank)) if supported else (j, ())
"""


@pytest.mark.parametrize(
    ("known", "owners", "mode_calls", "expected"),
    (
        ([7], 1, [], (7, (-7,))),
        ([], 2, [("scan", [7], [7], "physical")], (7, (7,))),
        ([], 3, [("scan", [7], [7], "physical")], (7, (7,))),
        ([], 1, [], (7, ())),
    ),
)
def test_revised_nomination_mode_selection(known, owners, mode_calls, expected):
    calls = []

    def build_modes(scan, labels, supported, mode):
        calls.append((scan, labels, supported, mode))
        return [7]

    scope = {"build_modes": build_modes}
    old = MODE_SELECTION.format(BEFORE)
    exec(old, scope)
    args = ({"scan": "scan"}, known, {"held_owners": owners}, 7)
    assert scope["vote"](*args) == expected
    if not known and owners == 1:
        assert calls == [("scan", [7], [], "physical")]
    calls.clear()
    new = revised(old)
    exec(new, scope)
    assert scope["vote"](*args) == expected
    assert calls == mode_calls


def test_overlay_refuses_unrecognized_or_duplicate_source():
    for invalid in ("", BEFORE + "\n" + BEFORE):
        with pytest.raises(ValueError, match="unexpected ranked fine nomination source"):
            revised(invalid)


def test_nomination_digest_preserves_tie_order_and_numeric_bits():
    common = dict(
        score=0.0,
        phase_s=0.125,
        phase_change_s=0.001,
        minimum_elevation_deg=11.0,
        conditional_RMS_hz=231.0,
        aliases=[0, 1],
        qualified=True,
        physical_modes=False,
    )
    row = dict(
        original_index=12,
        held_points=5,
        held_observation_ids=list("abcde"),
        coarse_candidate_count=50,
        candidates=[
            dict(common, candidate_index=12, norad=60000),
            dict(common, candidate_index=14, norad=60004),
        ],
        best=None,
    )
    baseline = dict(status="complete", families=[row])
    a = outcomes(baseline)
    assert a["families"] == 1 and a["candidate_counts"] == [2]
    modified = deepcopy(baseline)
    modified["families"][0]["candidates"].reverse()
    assert a["ordered_fine_outcomes_sha256"] != outcomes(modified)["ordered_fine_outcomes_sha256"]
    modified = deepcopy(baseline)
    modified["families"][0]["candidates"][0]["score"] = -0.0
    assert a["ordered_fine_outcomes_sha256"] != outcomes(modified)["ordered_fine_outcomes_sha256"]
