"""Verify and summarize all six conditional association-transfer shards."""
from __future__ import annotations

from dataclasses import asdict
import json
import math
from pathlib import Path

import numpy as np

import association_transfer_core as transfer
import association_transfer_reporting as reporting
from association_transfer_split import temporal_association_split
import run_association_transfer as runner


HERE = Path(__file__).resolve().parent
DIRECTIONS = ("A_to_B", "B_to_A")
MODES = ("normal", "reversed", "null")


def _hashable(value):
    if isinstance(value, list): return tuple(_hashable(item) for item in value)
    return value


def _close(actual, expected, path="root"):
    if isinstance(expected, dict):
        if not isinstance(actual, dict) or set(actual) != set(expected):
            raise ValueError(f"stored structure differs at {path}")
        for key in expected: _close(actual[key], expected[key], f"{path}.{key}")
    elif isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            raise ValueError(f"stored vector differs at {path}")
        for n,(left,right) in enumerate(zip(actual,expected)): _close(left,right,f"{path}[{n}]")
    elif isinstance(expected, (float,np.floating)):
        if not math.isfinite(float(actual)) or abs(float(actual)-float(expected)) > 1e-12:
            raise ValueError(f"stored numerical score differs at {path}")
    elif actual != expected: raise ValueError(f"stored value differs at {path}")


def _split_input(assignments):
    return [{key:(_hashable(value) if key in {"opportunity_key","physical_pair_key"} else value)
             for key,value in row.items() if key != "split_label"} for row in assignments]


def verify_split(saved):
    assignments=saved.get("observation_assignments",[])
    if not assignments: raise ValueError("split lacks provenance assignments")
    rebuilt=temporal_association_split(_split_input(assignments),guard_ns=saved.get("guard_ns"))
    _close(saved,runner.json_value(rebuilt),"split")
    # Independent edge audit: no global opportunity/pair key or same-group raw
    # interval overlap may cross train/A/B/guard labels.
    for key in ("opportunity_key","physical_pair_key"):
        labels={}
        for row in assignments:
            value=_hashable(row.get(key))
            if value is None: continue
            labels.setdefault(value,set()).add(row["split_label"])
        if any(len(value)>1 for value in labels.values()):
            raise ValueError("provenance key crosses split labels")
    for n,left in enumerate(assignments):
        for right in assignments[n+1:]:
            if (left["source_group_id"]==right["source_group_id"] and
                    left["sample_start"] < right["sample_end"] and
                    right["sample_start"] < left["sample_end"] and
                    left["split_label"] != right["split_label"]):
                raise ValueError("raw source interval crosses split labels")
    return rebuilt


def verify_track(track):
    ids=track.get("candidate_ids",[]);weights=track.get("training_log_weights",[])
    if len(ids)==0 or len(ids)!=len(weights) or len(set(ids))!=len(ids):
        raise ValueError("invalid track candidate inventory")
    split=verify_split(track.get("split",{}))
    if not split["supported"]: raise ValueError("supported track has unsupported split")
    directions=track.get("directions",{})
    if set(directions)!=set(DIRECTIONS): raise ValueError("missing reciprocal direction")
    records=[]
    for label in DIRECTIONS:
        value=directions[label]
        expected_condition=(split["A_observation_indices"] if label=="A_to_B"
                            else split["B_observation_indices"])
        expected_held=(split["B_observation_indices"] if label=="A_to_B"
                       else split["A_observation_indices"])
        if (value.get("conditioning_observation_indices")!=expected_condition or
                value.get("held_observation_indices")!=expected_held):
            raise ValueError("direction membership differs from split")
        fa=value.get("conditioning_frequency_log_likelihood",[])
        fb=value.get("held_frequency_log_likelihood",[])
        if len(fa)!=len(ids) or len(fb)!=len(ids): raise ValueError("frequency vector misaligned")
        if set(value.get("reception",{}))!=set(MODES) or set(value.get("quadrature",{}))!=set(MODES):
            raise ValueError("control inventory changed")
        controls={}
        for mode in MODES:
            stored=dict(value["reception"][mode]);ra=stored.pop("conditioning_reception_log_likelihood")
            if len(ra)!=len(ids): raise ValueError("reception vector misaligned")
            if mode == "null" and (not np.all(np.isfinite(ra)) or np.ptp(ra) > 1e-12):
                raise ValueError("candidate-independent control is not invariant")
            check=value["quadrature"][mode]
            discrepancy = float(check.get("maximum_candidate_loglik_absolute_difference", math.inf))
            if (not check.get("passed") or check.get("fit_order")!=64 or
                    check.get("verification_order")!=128 or
                    not math.isfinite(discrepancy) or not 0 <= discrepancy <= .001 or
                    float(check.get("tolerance", -.1))!=.001):
                raise ValueError("quadrature receipt changed")
            recalculated=transfer.association_transfer_score(
                ids,weights,fa,ra,fb,len(expected_held))
            _close(stored,recalculated,f"{label}.{mode}")
            controls[mode]={**recalculated,"conditioning_reception_log_likelihood":ra}
        if np.ptp(np.asarray(controls["null"]["conditioning_reception_log_likelihood"],float))>1e-12:
            raise ValueError("candidate-independent control is not invariant")
        record={"session_id":None,"track_id":track["track_id"],"direction":label,
            "candidate_ids":ids,"weight_seconds":track["weight_seconds"],
            "conditioning_count":len(expected_condition),"held_count":len(expected_held),
            "conditioning_frequency_log_likelihood":fa,"held_frequency_log_likelihood":fb,
            **controls}
        records.append(record)
    return records


def verify_shard_set(shards,sessions,expected_tracks=None):
    if len(shards)!=6 or len(sessions)!=6 or sorted(sessions)!=list(sessions):
        raise ValueError("expected six sorted calibration shards")
    held=[shard.get("held_session") for shard in shards]
    if sorted(held)!=list(sessions) or len(set(held))!=6:
        raise ValueError("missing or duplicate calibration fold")
    all_records=[];total_tracks=total_rows=0
    for shard in sorted(shards,key=lambda row:row["held_session"]):
        sid=shard["held_session"];supported=shard.get("tracks",[]);unsupported=shard.get("unsupported_tracks",[])
        ids=[row.get("track_id") for row in supported+unsupported]
        if len(ids)!=len(set(ids)): raise ValueError("duplicate supported/unsupported track")
        accounting=shard.get("accounting",{})
        if (accounting.get("session_tracks")!=len(ids) or
                accounting.get("supported_tracks")!=len(supported) or
                accounting.get("unsupported_tracks")!=len(unsupported)):
            raise ValueError("supported/unsupported accounting does not close")
        if expected_tracks is not None and set(ids)!=set(expected_tracks[sid]):
            raise ValueError("track inventory differs from frozen calibration")
        records=[]
        for row in supported:
            for record in verify_track(row): record["session_id"]=sid;records.append(record)
        for row in unsupported:
            split=verify_split(row["split"])
            if split["supported"]: raise ValueError("unsupported track has supported split")
        stored=shard.get("result_records",[])
        keys=[(row.get("session_id"),row.get("track_id"),row.get("direction")) for row in stored]
        if len(keys)!=len(set(keys)) or len(stored)!=2*len(supported):
            raise ValueError("duplicated or missing prediction directions")
        expected={(row["session_id"],row["track_id"],row["direction"]):row for row in records}
        actual={key:row for key,row in zip(keys,stored)}
        if set(actual)!=set(expected): raise ValueError("stored result-record membership changed")
        for key in expected:_close(actual[key],expected[key],"result_record")
        summary={label:runner.summarize([r for r in records if r["direction"]==label])
                 for label in DIRECTIONS}
        _close(shard.get("summaries"),summary,"shard_summary")
        total_tracks+=len(ids);total_rows+=int(accounting.get("session_reserve_rows",-1))
        all_records.extend(records)
    if total_tracks!=344 or total_rows!=6378:
        raise ValueError("six-shard 344-track/6378-row accounting changed")
    return all_records


def current_context():
    fixed_path=runner.LOCATION/"topology_frequency_fixedpoint.json"
    fixed_bytes=fixed_path.read_bytes();fixed=json.loads(fixed_bytes);sessions=sorted(fixed["final_tracks"])
    joined,receipt,calibration,cal_sha,detection,det_sha,ratio,ratio_sha=runner._accepted_sources(sessions)
    expected={sid:[track.track_id for track in joined if track.session_id==sid] for sid in sessions}
    inventory_bytes=(runner.DIRECTION/"evaluation_inventory.json").read_bytes()
    inventory={row["session_id"]:row for row in json.loads(inventory_bytes)}
    manifest_bytes=(runner.DIRECTION/"evaluation_manifest.json").read_bytes()
    directions_path=HERE/"calibration_directions_data.json"
    common={"frequency_parameters":fixed["frozen_final_parameters"],
        "calibration_sha256":cal_sha,"detection_aggregate_sha256":det_sha,
        "ratio_aggregate_sha256":ratio_sha,"input_source_hashes":receipt["source_hashes"],
        "evaluation_inventory_sha256":runner.digest(inventory_bytes),
        "evaluation_manifest_sha256":runner.digest(manifest_bytes),
        "calibration_directions_data_sha256":runner.digest(directions_path.read_bytes()),
        "protocol_sha256":runner.digest((HERE/"ASSOCIATION_TRANSFER_PROTOCOL.md").read_bytes()),
        "code_sha256":runner.source_hashes()}
    return sessions,expected,common,inventory,fixed,calibration,detection,ratio


def main():
    target=HERE/"association-transfer-summary.json"
    if target.exists():raise FileExistsError(target)
    sessions,expected,common,inventory,fixed,calibration,detection,ratio=current_context()
    shards=[];hashes={}
    for index,sid in enumerate(sessions):
        path=HERE/f"association-transfer-{sid}.json"
        if not path.exists():
            print(json.dumps({"complete":False,"pending_sessions":[s for s in sessions
                if not (HERE/f'association-transfer-{s}.json').exists()]}));return
        payload=path.read_bytes();shard=json.loads(payload);hashes[path.name]=runner.digest(payload)
        coefficients,det_fold,ratio_fold,sigma,tau=runner._fold_models(
            sid,sessions,calibration,detection,ratio)
        entry=inventory[sid];source=fixed["source_digests"][sid]
        if (not shard.get("finished") or shard.get("kind")!="calibration_only_conditional_association_transfer" or
                shard.get("session_index")!=index or shard.get("held_session")!=sid or
                any(shard.get(key)!=value for key,value in common.items()) or
                shard.get("cache_sha256")!=entry["cache_sha256"] or
                any(shard.get(key)!=source[key] for key in ("input_manifest_sha256",
                    "analysis_manifest_sha256","evidence_sha256","snapshot_digest","source_links_sha256")) or
                shard.get("coefficient_shard_sha256")!=runner.digest(
                    (HERE/f"mixture-calibration-polished-fold-{sid}.json").read_bytes()) or
                shard.get("detection_shard_sha256")!=detection["shard_sha256"][
                    f"track-random-intercept-refined-fold-{sid}.json"] or
                shard.get("ratio_shard_sha256")!=ratio["shard_sha256"][
                    f"ratio-random-intercept-fold-{sid}.json"] or
                shard.get("feature_schema")!=coefficients["feature_schema"] or
                shard.get("mixture_feature_names")!=coefficients["models"]["mixture"]["feature_names"] or
                float(shard.get("detection_sigma",math.nan))!=sigma or
                float(shard.get("ratio_tau",math.nan))!=tau):
            raise ValueError("association-transfer shard binding changed")
        shards.append(shard)
    records=verify_shard_set(shards,sessions,expected)
    output={"complete":True,"sessions":sessions,"records":records,
        "summary":reporting.cohort_summary(records,sessions),"shard_sha256":hashes,
        "source_hashes":common,
        "reporter_sha256":{name:runner.digest((HERE/name).read_bytes()) for name in (
            "score_association_transfer.py","association_transfer_reporting.py",
            "association_transfer_core.py","association_transfer_split.py")},
        "scope":"Calibration-only conditional association diagnostic; no geographic evaluation or satellite truth."}
    runner._atomic(target,output);print(json.dumps(output["summary"],indent=2))


if __name__=="__main__":main()
