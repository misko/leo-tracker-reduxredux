"""Exercise the geographic rule with controlled signed likelihoods."""

from importlib import import_module
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_context, recovery_inventory
from tools.pipeline_eval.variants.experimental import geographic_jackknife as gate

TRIAL = import_module("reports.ALGO08.v3.geographic_jackknife_trial")
GROUPS = tuple(range(8))


def quadratic(center):
    def loss(point):
        delta = np.asarray(point) - center
        return 2500 * (delta @ delta)

    return loss


@pytest.mark.parametrize(("center", "endpoint", "state"), (
    ([.6, .3], [.61, .27], "inside"),
    ([1.02, .0], [1., 0.], "unresolved"),
    ([1.2, .04], [1., 0.], "exterior"),
))
def test_unrestricted_position_and_certificates(center, endpoint, state):
    loss = quadratic(center)
    row = gate.diagnose(loss, lambda _: loss, GROUPS, endpoint, 1.)
    np.testing.assert_allclose(row["estimate_km"], center, atol=1e-12)
    assert row["likelihood_scale_km"] == pytest.approx([.02, .02])
    assert row["jackknife_scale_km"] == pytest.approx([0., 0.])
    assert row["state"] == state
    assert row["exterior_faces"] == (["east"] if state == "exterior" else [])


def test_satellite_influence_can_remove_a_likelihood_only_veto():
    loss = quadratic([1.2, 0.])

    def rebuilt(norad):
        return loss if norad is None else quadratic([1.2 + (-1)**norad * .2, 0.])

    row = gate.diagnose(loss, rebuilt, GROUPS, [1., 0.], 1.)
    assert row["estimate_km"] == pytest.approx([1.2, 0.])
    assert row["jackknife_scale_km"] == pytest.approx([.2 * np.sqrt(7), 0.])
    assert row["state"] == "unresolved"
    assert row["faces"]["east"]["upper_km"] > 0


def test_replay_mismatch_and_unsupported_groups_remain_unresolved():
    loss = quadratic([1.2, 0.])
    row = gate.diagnose(loss, lambda _: lambda p: loss(p) + 1., GROUPS, [1., 0.], 1.)
    assert row == dict(state="unresolved", reason="rebuilt_likelihood_mismatch")
    assert gate.diagnose(loss, lambda _: loss, (1, 2), [1., 0.], 1.) == dict(
        state="unresolved", reason="too_few_satellites"
    )
    assert gate.diagnose(loss, lambda _: loss, GROUPS, [0., 0.], 1.) == dict(
        state="unresolved", reason="unstable_local_extrapolation"
    )


def test_calibration_arms_must_certify_a_common_face():
    east = dict(state="exterior", exterior_faces=["east"])
    north = dict(state="exterior", exterior_faces=["north"])
    interior = dict(state="inside", exterior_faces=[])
    assert gate.paired_state(dict(c0=east, fitted_c=east)) == "exterior"
    assert gate.paired_state(dict(c0=east, fitted_c=north)) == "unresolved"
    assert gate.paired_state(dict(c0=east, fitted_c=interior)) == "unresolved"
    assert gate.paired_state(dict(c0=interior, fitted_c=interior)) == "inside"


def test_group_removal_excludes_both_receivers_and_predictive_entries(monkeypatch):
    keep = np.ones(6, bool)
    problem = SimpleNamespace(rows=[{"candidate_norad": i} for i in (12, 18, 12)],
                              slices=[slice(0, 2), slice(2, 4), slice(4, 6)],
                              keep=keep, reference=np.array([0.2, 0.3]))
    context = dict(scan=None, node=None, powers=None, means=None, model=None, families=[],
                   entries=[dict(norad=12), dict(norad=99)])

    def build(_scan, _node, mask, arm, reference, *_args):
        assert arm == "c0"
        assert reference is problem.reference
        return SimpleNamespace(mask=mask)

    monkeypatch.setattr(recovery_inventory, "make_event_problem", build)
    monkeypatch.setattr(recovery_inventory, "attach_event_predictive",
                        lambda p, entries, _: setattr(p, "entries", entries))
    monkeypatch.setattr(reassociation_context, "objective",
                        lambda p, *_: (p.mask.tolist(), p.entries))
    _, rebuild, groups = TRIAL.selected_likelihood(context, "c0", problem)
    assert groups == [12, 18, 99]
    assert rebuild(12)(None) == ([False, False, True, True, False, False], [dict(norad=99)])
    assert rebuild(None)(None) == ([True] * 6, context["entries"])
    assert keep.all()


def test_local_gaussian_scale_limits_discrimination():
    result = gate.separation_control(1.0)
    assert result["separation_sigma"] == .2
    assert result["equal_prior_error"] == pytest.approx(.460172, abs=1e-6)
    assert result["power_at_5pct_false_withhold"] == pytest.approx(.07425, abs=1e-4)


@pytest.mark.parametrize("site", ("north", "south"))
def test_close_omission_verifies_the_archived_signed_output(site):
    digest = TRIAL.SAVED_OUTSIDE[site]
    path = TRIAL.MEASUREMENTS / f"exact-curved-lookahead-{site}-offers.json"
    archived = TRIAL.verified(path, digest)
    case = archived["results"][f"{site}-mirror-outside"]
    row = dict(archive=archived["archive"], source_sha256=archived["native_sha256"],
               pair_sha256=archived["pair_sha256"], solver_specification=archived["specification"],
               offer=case["offer"], signed=case | {"evidence": case["science"]})
    assert TRIAL.require_saved_outside(site, row) == digest
    row["signed"]["owners"] = {"c0": "changed"}
    with pytest.raises(ValueError, match="archived signed v3 solve"):
        TRIAL.require_saved_outside(site, row)
