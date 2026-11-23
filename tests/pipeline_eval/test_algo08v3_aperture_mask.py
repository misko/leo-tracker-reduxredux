from importlib import import_module

import pytest


aperture = import_module("reports.ALGO08.v3.aperture_mask")


def native(visits, *, blank=(), weak=(), cadence=2_500_000):
    probes = []
    for visit, (edge, channel, rf) in enumerate(visits):
        for antenna in (0, 1):
            factor = dict(fractional_margin=0.099 if (visit, antenna) in weak else 0.1,
                          fractional_tracking_cfo_hz=100_000 + visit * 10,
                          candidate_rank=0)
            probes.append(dict(edge=edge, channel=channel, actual_rf_hz=rf,
                               visit_index=visit, receiver_id=antenna,
                               valid_start_counter=visit * cadence,
                               candidates=[] if (visit, antenna) in blank else [factor]))
    return dict(clock_anchor=dict(sample_counter=0), source=dict(sample_rate_hz=10_000_000,
                raw_recording_authority_digest="raw", analysis_manifest_sha256="original", probes=probes),
                provenance=dict(detector_sha256="sha256:frozen", processed_windows=len(visits)))


def test_interleaving_preserves_stereo_opportunities_counters_and_every_rf_edge():
    first = ("lower", 1, 100)
    second = ("lower", 1, 101)
    third = ("upper", 1, 100)
    fourth = ("lower", 2, 100)
    parent = native([first, second, third, fourth] * 10)
    candidate, audit = aperture.masked(parent, "fixed")
    assert audit["dropped"] == [16, 17, 18, 19, 32, 33, 34, 35]
    assert audit["rf_groups"] == 4
    assert audit["resulting_observations"] == 64
    assert candidate["source"]["raw_recording_authority_digest"] == "raw"
    assert candidate["source"]["analysis_manifest_sha256"] != "original"
    assert candidate["provenance"]["processed_windows"] == 40
    for old, new in zip(parent["source"]["probes"], candidate["source"]["probes"], strict=True):
        assert dict(old, candidates=[]) == dict(new, candidates=[])
        assert new["candidates"] == ([] if old["visit_index"] in audit["dropped"] else old["candidates"])


def test_quality_escalation_is_causal_and_either_lane_can_force_it():
    visits = [("lower", 2, 300)] * 11
    causal, audit = aperture.masked(native(visits, weak={(3, 1), (4, 1)}), "guarded")
    _, changed_future = aperture.masked(native(visits, weak={(3, 1)}), "guarded")
    assert audit["escalated"] == changed_future["escalated"] == [4]
    assert audit["dropped"] == changed_future["dropped"] == [8]
    assert causal["source"]["probes"][9]["candidates"][0]["fractional_margin"] == 0.099
    _, aged = aperture.masked(native(visits, cadence=90_000_000), "guarded")
    assert aged["escalated"] == [4, 8]
    _, too_close = aperture.masked(native(visits, cadence=400_000), "guarded")
    assert too_close["escalated"] == [4, 8]


def test_reselection_cannot_use_a_skipped_carrier_as_a_donor():
    visits = [("lower", 1, 100)] * 8
    # Visit 5 can publish only with its three donors at 1, 3 and 4.
    blank = {(i, a) for i in (0, 2) for a in (0, 1)}
    parent = native(visits, blank=blank)
    full, _ = aperture.masked(parent, "full", reselect=True)
    fixed, _ = aperture.masked(parent, "fixed", reselect=True)
    assert full["source"]["probes"][10]["candidates"]
    assert not fixed["source"]["probes"][10]["candidates"]


def test_rejects_mismatched_stereo_metadata():
    parent = native([("lower", 1, 100)] * 2)
    parent["source"]["probes"][1]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="ordered antenna rows"):
        aperture.masked(parent, "fixed")
