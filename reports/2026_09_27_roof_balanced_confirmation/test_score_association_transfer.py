from copy import deepcopy

import numpy as np
import pytest

import association_transfer_core as core
from association_transfer_split import temporal_association_split
import run_association_transfer as runner
from score_association_transfer import verify_shard_set


SESSIONS=[f"s{i}" for i in range(6)]


def make_track(tid):
    split=temporal_association_split([
        {"observation_index":0,"observation_id":f"{tid}-a","utc_ns":0,
         "training":False,"source_group_id":f"g-{tid}","sample_start":0,
         "sample_end":10,"opportunity_key":None,"physical_pair_key":None},
        {"observation_index":1,"observation_id":f"{tid}-b","utc_ns":1_000_000_000,
         "training":False,"source_group_id":f"g-{tid}","sample_start":20,
         "sample_end":30,"opportunity_key":None,"physical_pair_key":None}])
    ids=[1,2];weights=np.log([.4,.6]).tolist();directions={}
    for label,fa,fb in (("A_to_B",[-.2,-1.],[-1.,-.1]),
                        ("B_to_A",[-1.,-.1],[-.2,-1.])):
        controls={};quadrature={}
        for mode,ra in (("normal",[.4,-.2]),("reversed",[-.1,.3]),("null",[2.,2.])):
            value=core.association_transfer_score(ids,weights,fa,ra,fb,1)
            controls[mode]={**value,"conditioning_reception_log_likelihood":ra}
            quadrature[mode]={"fit_order":64,"verification_order":128,
                "maximum_candidate_loglik_absolute_difference":0.,"tolerance":.001,"passed":True}
        condition=split["A_observation_indices"] if label=="A_to_B" else split["B_observation_indices"]
        held=split["B_observation_indices"] if label=="A_to_B" else split["A_observation_indices"]
        directions[label]={"conditioning_observation_indices":condition,
            "held_observation_indices":held,"conditioning_frequency_log_likelihood":fa,
            "held_frequency_log_likelihood":fb,"reception":controls,"quadrature":quadrature}
    return {"track_id":tid,"candidate_ids":ids,"training_log_weights":weights,
            "profiled_cfo_hz":[0.,0.],"weight_seconds":2,"split":split,"directions":directions}


def flatten(sid,track):
    rows=[]
    for label in ("A_to_B","B_to_A"):
        direction=track["directions"][label]
        rows.append({"session_id":sid,"track_id":track["track_id"],"direction":label,
            "candidate_ids":track["candidate_ids"],"weight_seconds":track["weight_seconds"],
            "conditioning_count":len(direction["conditioning_observation_indices"]),
            "held_count":len(direction["held_observation_indices"]),
            "conditioning_frequency_log_likelihood":direction["conditioning_frequency_log_likelihood"],
            "held_frequency_log_likelihood":direction["held_frequency_log_likelihood"],
            **direction["reception"]})
    return rows


def cohort():
    # Exact required totals: four sessions x57 and two x58 =344 tracks;
    # reserve-row accounting is an independent frozen-session receipt.
    counts=[57,57,57,57,58,58];row_counts=[1063]*5+[1063]
    # Adjust the final session to exact 6,378 total (6*1,063).
    shards=[];expected={}
    for sid,count,reserve in zip(SESSIONS,counts,row_counts):
        tracks=[make_track(f"{sid}-t{n}") for n in range(count)]
        expected[sid]=[row["track_id"] for row in tracks]
        records=[item for track in tracks for item in flatten(sid,track)]
        shards.append({"held_session":sid,"tracks":tracks,"unsupported_tracks":[],
            "result_records":records,"accounting":{"session_tracks":count,
                "session_reserve_rows":reserve,"supported_tracks":count,"unsupported_tracks":0},
            "summaries":{label:runner.summarize([r for r in records if r["direction"]==label])
                         for label in ("A_to_B","B_to_A")}})
    return shards,expected


def test_complete_fake_six_fold_cohort_closes_and_reproduces_scores():
    shards,expected=cohort();records=verify_shard_set(shards,SESSIONS,expected)
    assert len(records)==2*344


def test_missing_or_duplicate_fold_rejected():
    shards,expected=cohort()
    with pytest.raises(ValueError,match="six sorted|fold"):
        verify_shard_set(shards[:-1],SESSIONS,expected)
    changed=deepcopy(shards);changed[-1]["held_session"]=changed[0]["held_session"]
    with pytest.raises(ValueError,match="fold"):
        verify_shard_set(changed,SESSIONS,expected)


def test_noncanceling_null_control_rejected():
    shards,expected=cohort();track=shards[0]["tracks"][0]
    track["directions"]["A_to_B"]["reception"]["null"][
        "conditioning_reception_log_likelihood"]=[0.,1.]
    with pytest.raises(ValueError,match="candidate-independent"):
        verify_shard_set(shards,SESSIONS,expected)


def test_corrupt_flat_score_rejected():
    shards,expected=cohort()
    shards[0]["result_records"][0]["normal"]["reception_mean_nll"]+=.1
    with pytest.raises(ValueError,match="stored numerical score"):
        verify_shard_set(shards,SESSIONS,expected)
