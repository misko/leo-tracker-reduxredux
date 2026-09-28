#!/usr/bin/env python3
"""Read-only bounded replay for shared proposals, clocks, and receiver location."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path

import numpy as np

from joint_core import TrackPrediction, profile_track, rank_hypotheses, score_profiled_location
from leo.analysis.adaptive_tle_prediction import RegionalTrackPredictionEvaluator, build_prediction_banks
from leo.analysis.adaptive_tle_prediction import ReceiverPoint
from leo.operations.adaptive_tle_position_inputs import prepare_adaptive_tle_position_inputs
from leo.operations.tle_archive import TleArchiveReader
from leo.sky.frames import geodetic_to_ecef_km
from leo.storage.adaptive_tle_position import AdaptiveTlePositionStoreV2
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

REFERENCE = (37.84903264307456, -122.4856541910174)
MODELS = (("lambda_0", 0.0, False), ("lambda_100", 100.0, False), ("lambda_1000", 1_000.0, False), ("lambda_10000", 10_000.0, False), ("hard_shared", 0.0, True))


def distance_km(a, b):
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    q = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*6371.0088*math.asin(math.sqrt(min(1.0, q)))


def local(center, point):
    lat1, lon1, lat2, lon2 = map(math.radians, (*center, *point))
    dlon = lon2-lon1
    bearing = math.atan2(math.sin(dlon)*math.cos(lat2), math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(dlon))
    d = distance_km(center, point)
    return d*math.sin(bearing), d*math.cos(bearing)


def coordinates(latitude_deg, longitude_deg, east_km, north_km):
    angular=np.hypot(east_km,north_km)/6371.0088
    bearing=np.arctan2(east_km,north_km)
    lat0,lon0=np.deg2rad([latitude_deg,longitude_deg])
    latitude=np.arcsin(np.sin(lat0)*np.cos(angular)+np.cos(lat0)*np.sin(angular)*np.cos(bearing))
    longitude=lon0+np.arctan2(np.sin(bearing)*np.sin(angular)*np.cos(lat0),np.cos(angular)-np.sin(lat0)*np.sin(latitude))
    return float(np.rad2deg(latitude)),float((np.rad2deg(longitude)+180)%360-180)


def point_factory(latitude_deg, longitude_deg):
    def point(east_km,north_km):
        latitude,longitude=coordinates(latitude_deg,longitude_deg,east_km,north_km)
        lat,lon=np.deg2rad([latitude,longitude])
        return ReceiverPoint(geodetic_to_ecef_km(latitude,longitude,0),np.asarray([np.cos(lat)*np.cos(lon),np.cos(lat)*np.sin(lon),np.sin(lat)]))
    return point


def load_document(store, session_id):
    status=store.status(session_id)
    if status.manifest is None:
        raise ValueError(f"{session_id}: published adaptive position document absent")
    return status.manifest.document.model_dump(mode="json"), status.manifest.document_sha256


def proposals(documents):
    """Frozen conditional inventory: exact group published winners only, no truth."""
    output = {}
    for document in documents:
        for prior in document["priors"]:
            selected = prior["selected"]
            center = (selected["latitude_deg"], selected["longitude_deg"])
            lat, lon = center
            key = (round(lat, 8), round(lon, 8))
            output.setdefault(key, {"latitude_deg": lat, "longitude_deg": lon, "sources": []})["sources"].append({"session_id": document["session_id"], "prior": prior["name"]})
    return [{"location_id": f"conditional-{index:03d}", **row} for index, (_, row) in enumerate(sorted(output.items()))]


def convert_blocks(blocks):
    grouped = {}
    for block in blocks:
        grouped.setdefault(block.track_id, []).append(block)
    answer = []
    for track_id in sorted(grouped):
        rows = grouped[track_id]
        first = rows[0]
        candidates, prediction, visible = [], [], []
        for block in rows:
            candidates.extend(map(str, block.candidate_ids))
            prediction.append(np.asarray(block.predictions_hz))
            v = np.asarray(block.visible)
            visible.append(np.broadcast_to(v[:, None], (len(v), len(block.taus_s))) if v.ndim == 1 else v)
        answer.append(TrackPrediction(track_id, len(np.unique(np.floor(first.times_s).astype(int))), tuple(candidates), np.asarray(first.taus_s), np.asarray(first.measured_hz), np.concatenate(prediction), np.asarray(first.training_mask), np.concatenate(visible)))
    return answer


def production_hard_score(blocks):
    """Exact legacy held-out identity/tau/CFO selection for parity only."""
    total = loss = 0.0
    for track in convert_blocks(blocks):
        residual = track.measured_hz[None,None,:] - track.predicted_hz
        train = track.training_mask
        cfo = residual[:,:,train].mean(axis=2)
        centered = residual-cfo[:,:,None]
        train_rms = np.sqrt(np.mean(centered[:,:,train]**2, axis=2))
        train_rms = np.where(track.visible, train_rms, np.inf)
        held = np.sqrt(np.mean(centered[:,:,~train]**2, axis=2))
        # Legacy rule: choose tau on training independently for each identity,
        # then rank those identity rows by held-out RMS.
        tau_by_candidate = np.argmin(train_rms, axis=1)
        values = held[np.arange(len(tau_by_candidate)), tau_by_candidate]
        values = np.where(np.isfinite(train_rms[np.arange(len(tau_by_candidate)), tau_by_candidate]), values, np.inf)
        value = float(np.min(values))
        loss += track.weight_s * min(800.0, value)**2
        total += track.weight_s
    return math.sqrt(loss/total)


def analyze_group(bulk_root, tle_root, group):
    started = time.monotonic()
    raw_sessions = group.get("session_ids", group.get("sessions"))
    session_ids = [sid if sid.startswith("scan-fw-") else "scan-fw-"+sid for sid in raw_sessions]
    published=AdaptiveTlePositionStoreV2(bulk_root)
    loaded=[load_document(published,sid) for sid in session_ids]
    documents=[row[0] for row in loaded]
    points = proposals(documents)
    per_location = {point["location_id"]: [] for point in points}
    bindings, parity = [], []
    for sid, (_, document_digest), document in zip(session_ids, loaded, documents, strict=True):
        store = ScannerTrackingInputStore(bulk_root)
        try:
            prepared = prepare_adaptive_tle_position_inputs(sid, inputs=store, archive=TleArchiveReader(tle_root))
        finally:
            store.close()
        if prepared.evidence_sha256 != document["evidence_sha256"] or prepared.snapshot_digest != document["diagnostics"]["snapshot_digest"]:
            raise ValueError(f"{sid}: saved evidence/snapshot parity failure")
        banks, receipt = build_prediction_banks(prepared.catalogue, prepared.candidate_indices, prepared.start_utc_ns, prepared.tracks)
        # One arbitrary geometry origin is valid; evaluator receives local offsets.
        origin = (points[0]["latitude_deg"], points[0]["longitude_deg"])
        evaluator = RegionalTrackPredictionEvaluator(banks, point_factory(*origin))
        block_cache = {}
        for point in points:
            east, north = local(origin, (point["latitude_deg"], point["longitude_deg"]))
            blocks = tuple(evaluator(east, north))
            block_cache[point["location_id"]] = blocks
            tracks = convert_blocks(blocks)
            compact = [(track.weight_s, track.taus_s, profile_track(track)) for track in tracks]
            per_location[point["location_id"]].append((sid, compact))
        for prior in document["priors"]:
            expected = prior["selected"]
            nearest = min(points, key=lambda p: distance_km((p["latitude_deg"],p["longitude_deg"]),(expected["latitude_deg"],expected["longitude_deg"])))
            point_error = distance_km((nearest["latitude_deg"],nearest["longitude_deg"]),(expected["latitude_deg"],expected["longitude_deg"]))
            if point_error > 1e-5:
                raise ValueError(f"{sid}/{prior['name']}: exact published point absent ({point_error} km)")
            replay = production_hard_score(block_cache[nearest["location_id"]])
            difference = replay-expected["capped_weighted_rmse_hz"]
            if abs(difference)>1e-5:
                raise ValueError(f"{sid}/{prior['name']}: production-hard replay differs by {difference} Hz")
            parity.append({"session_id":sid,"prior":prior["name"],"replayed_score_hz":replay,"published_score_hz":expected["capped_weighted_rmse_hz"],"published_horizontal_error_km":expected["horizontal_error_m"]/1000,"difference_hz":difference})
        bindings.append({"session_id":sid,"document_sha256":document_digest,"evidence_sha256":prepared.evidence_sha256,"snapshot_digest":prepared.snapshot_digest,"candidate_count":receipt.candidate_count,"track_count":receipt.track_count})
    hypotheses=[]
    point_by_id={p["location_id"]:p for p in points}
    for location_id, scans in per_location.items():
        for model, penalty, hard in MODELS:
            value=score_profiled_location(scans, penalty, hard_shared=hard)
            scan_scores=[score_profiled_location([scan],penalty,hard_shared=hard) for scan in scans]
            value["scan_normalized_training_rms_hz"]=float(np.sqrt(np.mean([x["training_capped_weighted_rms_hz"]**2 for x in scan_scores])))
            value["scan_normalized_reserved_rms_hz"]=float(np.sqrt(np.mean([x["reserved_capped_weighted_rms_hz"]**2 for x in scan_scores])))
            hypotheses.append({**point_by_id[location_id],"model":model,"penalty_hz2_per_s2":penalty,**value})
    # Control: each scan selects its own lambda-0 location; coordinates remain separate.
    independent=[]
    for scan_index,sid in enumerate(session_ids):
        choices=[]
        for point in points:
            value=score_profiled_location([per_location[point["location_id"]][scan_index]],0.0)
            choices.append({**point,"session_id":sid,**value})
        independent.append(min(choices,key=lambda row:(row["training_capped_weighted_rms_hz"],row["location_id"])))
    top={}
    for model,_,_ in MODELS:
        top[model]=rank_hypotheses([row for row in hypotheses if row["model"]==model],5,"regularized_equal_scan_rms_hz")
    # Geographic truth is appended only after all training-only rankings are frozen.
    for row in hypotheses:
        row["reference_error_km"]=distance_km((row["latitude_deg"],row["longitude_deg"]),REFERENCE)
    for row in independent:
        row["reference_error_km"]=distance_km((row["latitude_deg"],row["longitude_deg"]),REFERENCE)
    return {"group_id":group["group_id"],"role":group.get("role"),"session_ids":session_ids,"proposal_count":len(points),"elapsed_s":time.monotonic()-started,"bindings":bindings,"production_hard_parity":parity,"independent_scan_lambda_0_control":independent,"top_hypotheses":top,"hypotheses":hypotheses}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--groups",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--bulk-root",type=Path,default=Path("/srv/bulk/leo"))
    parser.add_argument("--tle-root",type=Path,default=Path("/var/lib/leo/tle"))
    args=parser.parse_args()
    group_document=json.loads(args.groups.read_text())
    core_path=Path(__file__).with_name("joint_core.py")
    payload={"schema":"joint-location-prototype/v1","protocol":{"conditional_inventory":True,"independent_acquisition_claimed":False,"proposal_source":"union of exact group published prior winners only; leakage-prone retrospective diagnostic","models":[x[0] for x in MODELS],"selection":"training-only; reserved reported only","top_k_complete_hypotheses":5,"primary_weighting":"equal-scan normalized penalized training objective with occupied-second weights within scan; never compared across models","sensitivity_weighting":"duration pooled with fixed all-track denominator","production_hard_arm":"exact legacy held-out winner replay at published locations; parity only","group_assignment_seed":group_document.get("random_seed",group_document.get("seed")),"group_manifest_sha256":"sha256:"+hashlib.sha256(args.groups.read_bytes()).hexdigest(),"runner_sha256":"sha256:"+hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),"core_sha256":"sha256:"+hashlib.sha256(core_path.read_bytes()).hexdigest()},"groups":[]}
    for group in group_document["groups"]:
        result=analyze_group(args.bulk_root,args.tle_root,group)
        payload["groups"].append(result)
        args.output.write_text(json.dumps(payload,indent=2)+"\n")
        print(group["group_id"],f"{result['elapsed_s']:.1f}s",flush=True)


if __name__=="__main__": main()
