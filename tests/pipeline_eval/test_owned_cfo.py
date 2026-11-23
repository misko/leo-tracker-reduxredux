from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from reports.ALGO08.v3.owned_cfo_finish import CFO, OwnedCfo, matching_values, revised_inputs, views


def test_paired_view_rejects_epoch_and_anchor_edits():
    probes = [dict(receiver_id=0, valid_start_counter=n, edge="upper", actual_rf_hz=11500000000., channel=1,
                   visit_index=n, candidates=[{CFO: -31_420., "passed_fractional_margin_gate": True, "epoch": 11}])
              for n in (20, 40)]
    before = dict(source=dict(session_id="signed", probes=probes), provenance={})
    after = deepcopy(before)
    oid = "sha256:" + sha256(b"signed:0:40").hexdigest()
    after["source"]["probes"][1]["candidates"][0][CFO] = -31_510.
    _, positives, changed = views(before, after, ("full", "short_primary"))
    assert positives == {oid: (40, 0)} and changed == {oid: -31_510.}
    after["source"]["probes"][1]["candidates"][0]["epoch"] += 1
    with pytest.raises(ValueError, match="only signed CFO"):
        views(before, after, ("full", "short_primary"))
    after = deepcopy(before)
    after["source"]["probes"][0]["candidates"][0][CFO] = -31_510.
    with pytest.raises(ValueError, match="changed full-aperture anchor"):
        views(before, after, ("full", "short_primary"))


def test_replacement_keeps_original_integral_alias_and_unowned_points():
    period = 1 / 4.4e-6
    track = {"observation_ids": ["first", "second"], "values": np.array([10.5 - 2*period, -20.5])}
    before, after = {"first": 10.5, "second": -20.5}, {"first": 20.75, "second": -12.0}
    values, edited = matching_values(track, {"first"}, before, after, period)
    assert edited == {"first"}
    assert values.tolist() == [20.75 - 2*period, -20.5]
    assert track["values"].tolist() == [10.5 - 2*period, -20.5]
    with pytest.raises(ValueError, match="original alias lift"):
        matching_values(track, {"first"}, {"first": 11.5}, after, period)


def test_staged_clone_leaves_original_evidence_available_for_fallback():
    old = {"key": "track", "values": np.array([4., 9.]), "observation_ids": ["owned", "unowned"]}
    observations = [dict(observation_id=oid, measured_cfo_hz=value)
                    for oid, value in zip(old["observation_ids"], old["values"], strict=True)]
    scan = SimpleNamespace(tracks=[old], groups=[("track", [old])], reference={}, element_derivatives={})
    prepared = {"tracks": {"tracks": scan.tracks, "observations": observations}}
    incumbent = {"scan": scan, "keep": np.array([True, False])}
    changed, trial = revised_inputs(prepared, incumbent, {"owned"}, {"owned": 4.}, {"owned": 21.}, 120.)
    assert changed["tracks"]["observations"][0]["measured_cfo_hz"] == 21.
    assert trial["scan"].groups[0][1][0]["values"].tolist() == [21., 9.]
    assert prepared["tracks"]["observations"][0]["measured_cfo_hz"] == 4.
    assert scan.tracks[0]["values"].tolist() == [4., 9.]
    assert trial["keep"] is incumbent["keep"]


def test_selected_packet_must_carry_a_bound_observed_frequency():
    policy = OwnedCfo.__new__(OwnedCfo)
    policy.before, policy.refined, policy.evidence = {"one": 12.}, {"one": 73.}, []
    row = dict(observation_id="one", measured_cfo_hz=73.)
    packet = {"rows": {"c0": [row], "fitted_c": [row]}}
    assert policy.emitted(packet) is packet and policy.evidence[-1] == {"c0": ["one"], "fitted_c": ["one"]}
    with pytest.raises(ValueError, match="unbound CFO"):
        policy.emitted({"rows": {"c0": [dict(row, measured_cfo_hz=8.)]}})
