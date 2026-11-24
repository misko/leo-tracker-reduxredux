from copy import deepcopy
from hashlib import sha256

import pytest

from reports.ALGO08.v3.three_quarter_owner_attribution import (
    classify,
    cold_forensics,
    digest,
    native_locations,
    ownership,
)


def test_owner_accounting_partitions_deleted_and_retained_native_opportunities():
    locations = {oid: ("0", oid.startswith("deleted")) for oid in
                 ("deleted_owned", "deleted_unowned", "same", "switch", "disappear", "new", "neither")}
    locations["new"] = ("1", False)
    before = {"deleted_owned": 3, "same": 3, "switch": 3, "disappear": 5}
    after = {"same": 3, "switch": 5, "new": 5}
    result = classify(locations, before, after)
    assert sum(result["totals"].values()) == len(locations)
    assert set(result["totals"].values()) == {1}
    assert result["by_segment"]["1"] == {"newly_assigned": 1}
    assert result["by_satellite"]["3"] == {"ordinary": 3, "sampled": 1, "deleted_owned": 1,
                                             "switched_out": 1, "same_satellite": 1}
    assert result["by_satellite"]["5"] == {"ordinary": 1, "sampled": 2, "switched_in": 1,
                                             "unassigned_after": 1, "newly_assigned": 1}
    assert result["transitions"] == [{"before": 3, "after": 5, "count": 1}]
    with pytest.raises(ValueError, match="omitted native lane"):
        classify(locations, before, dict(after, deleted_unowned=3))
    with pytest.raises(ValueError, match="absent from original"):
        classify(locations, before, dict(after, fabricated=3))


def test_join_uses_signed_short_tail_boundaries_and_exact_retained_factor_rows():
    members = [dict(ordinal=ordinal, first_visit=start, stop_visit=stop, window_count=stop-start,
                    observed_index_sha256="index", index_sha256="index", manifest_sha256="manifest",
                    segment_manifest=f"/sealed/recording-segment-{segment}/manifest.json", omit=omit)
               for ordinal, (segment, start, stop, omit) in enumerate((("00", 0, 3, False), ("01", 3, 67, True),
                                                                       ("01", 67, 69, False)))]
    probes = [dict(visit_index=visit, receiver_id=rx, valid_start_counter=10+visit, candidates=[{"cfo": 1000}])
              for visit, rx in ((2, 0), (3, 1), (67, 0))]
    authority = dict(session_id="session", raw_authority_sha256="recording", inventory_sha256="inv", window_count=69)
    ordinary = dict(clock_anchor=[1], delivery_clocks=[2], source=dict(
        session_id="session", raw_recording_authority_digest="recording", input_manifest_sha256="inv", probes=probes))
    sampled = deepcopy(ordinary)
    sampled["source"]["probes"].pop(1)
    sampled["provenance"] = dict(research_sampling=dict(members_sha256=digest(members),
                                                        skipped_acquisition_windows=list(range(3, 67)), receiver_slots=[0, 1]))
    _, locations = native_locations(ordinary, sampled, members, authority)
    assert locations == {"sha256:" + sha256(key.encode()).hexdigest(): at for key, at in
                         (("session:0:12", ("00", False)), ("session:1:13", ("01", True)), ("session:0:77", ("01", False)))}
    sampled["source"]["probes"][-1]["candidates"][0]["cfo"] += 1
    with pytest.raises(ValueError, match="retained native factors"):
        native_locations(ordinary, sampled, members, authority)


def test_reject_owner_digest_even_when_overwritten_duplicates_keep_same_map():
    evidence = dict(owner_rows=dict(c0=[["a", 10, "conditional"]]),
                    detail=dict(arms=dict(c0=dict(owner_sha256=digest({"a": 10}), associated_points=1))))
    assert ownership(evidence, "c0") == {"a": 10}
    evidence["owner_rows"]["c0"].append(["a", 10, "conditional"])
    with pytest.raises(ValueError, match="sealed publication"):
        ownership(evidence, "c0")


def test_cold_finalist_marks_postsalvage_rejection_and_checks_rank_pairing():
    rank = dict(ranked_nodes=1, finalist_signatures=[[['track', 7, 123, 1]]])
    cold = dict(branch=1, east_north_km=[3, 0], scores=[10], routing="all_finalists",
                prefix=[dict(branch=1, parameters=[1, 0], evaluations=5)],
                completed=[dict(branch=1, point=[3, 0], labels=[7], score=10)])
    support = dict(cold_rejected_tracks=[], second_curved_rejections=["track"])
    witness = dict(ports=dict(history_risk=dict(two_centre_rank=rank, nomination_handoff={},
                                               lean_attempts=[dict(cold=cold, support=support, pair_passes=True)])))
    result = cold_forensics(witness, [0, 0], {123})
    assert result["finalists"][0]["completed_to_ordinary_c0_km"] == 3
    assert result["selected_lost_satellite_tracks"] == [dict(component="track", norad=123, alias=1,
                                                              cold_rejected=False, second_curved_rejected=True)]
    cold["completed"][0]["labels"] = [8]
    with pytest.raises(ValueError, match="completed cold fits disagree"):
        cold_forensics(witness, [0, 0], {123})
