"""Read-only evaluation-reference audit, never imported by localization.

Reads sealed recording metadata and existing capture-pose companions only.
Prints an audit to stdout; it never writes to the recording corpus.
"""

import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def canonical_digest(document):
    payload=json.dumps(document,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    return "sha256:"+hashlib.sha256(payload).hexdigest()


def verify_pose(document,session_id,manifest_digest):
    content={k:v for k,v in document.items() if k!="binding_digest"}
    if canonical_digest(content)!=document["binding_digest"]:raise ValueError("pose binding digest mismatch")
    if canonical_digest(document["pose_authority"])!=document["pose_authority_digest"]:
        raise ValueError("pose authority digest mismatch")
    if document["session_id"]!=session_id or document["manifest_sha256"]!=manifest_digest:
        raise ValueError("pose does not own this immutable recording")
    a=document["pose_authority"]
    if not a["valid_from_utc_ns"]<=document["capture_start_earliest_utc_ns"]<=document["capture_end_utc_ns"]<a["valid_until_utc_ns"]:
        raise ValueError("pose validity does not cover capture")


def run():
    source=ROOT/"reports/2026_10_18_ds23_post_ds22/manifest.json"
    manifest=json.loads(source.read_text());rows=[]
    authority_path=ROOT/"deploy/station/gauss-r20-lt3d-004b-20261001-v1.json"
    authority=json.loads(authority_path.read_text())
    for member in manifest["members"]:
        row=dict(case=member["dataset_label"],format=member["recording_format"],radio_serials=[],
            radio_ids=[],lnb_lo_hz=[],all_raw_metadata_digests_match=True,pose_binding_verified=False)
        embedded=None
        for segment in member["raw_recording"]["segments"]:
            payload=Path(segment["path"]).read_bytes()
            if "sha256:"+hashlib.sha256(payload).hexdigest()!=segment["sha256"]:
                raise ValueError("sealed metadata changed: "+member["dataset_label"])
            raw=json.loads(payload)
            if "manifest" in raw:
                body=raw["manifest"];receipt=body["receipt"];geometry=receipt["plan"]["geometry"]
                serial=receipt["radio_serial"];radio_id=receipt["radio_id"];los=[geometry["lnb_lo_hz"]]
                embedded=raw["sha256"]
            else:
                serial=raw["radio"]["serial"];radio_id=None
                los=[t["lnb_lo_hz"] for t in raw["configuration"]["targets"]]
            row["radio_serials"].append(serial)
            if radio_id:row["radio_ids"].append(radio_id)
            row["lnb_lo_hz"].extend(los)
        for name in ("radio_serials","radio_ids","lnb_lo_hz"):row[name]=sorted(set(row[name]))
        row["same_radio_as_roof_authority"]=row["radio_serials"]==[authority["radio_serial"]]
        row["capture_start_within_authority_interval"]=authority["valid_from_utc_ns"]<=member["captured_utc_ns"]<authority["valid_until_utc_ns"]
        if embedded is not None:
            companion=Path("/srv/bulk/leo/capture-pose")/authority["revision"]/(member["session_id"]+".json")
            row["existing_pose_companion_present"]=companion.exists()
            if companion.exists():
                pose=json.loads(companion.read_text());verify_pose(pose,member["session_id"],embedded)
                row.update(pose_binding_verified=True,pose_authority_revision=pose["pose_authority"]["revision"],
                    pose_latitude_deg=pose["pose_authority"]["latitude_deg"],pose_longitude_deg=pose["pose_authority"]["longitude_deg"],
                    altitude_m=pose["pose_authority"]["altitude_m"])
        rows.append(row)
    # Reference comparison belongs exclusively to this evaluation auditor.
    supplied=(37.849061591561885,-122.48574968092912)
    roof=(authority["latitude_deg"],authority["longitude_deg"])
    lat1,lat2=map(math.radians,(supplied[0],roof[0]));dlon=math.radians(supplied[1]-roof[1])
    h=math.sin((lat1-lat2)/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    distance=12742000*math.asin(math.sqrt(h))
    result=dict(rows=rows,recordings=len(rows),formats=dict(Counter(r["format"] for r in rows)),
        all_metadata_digests_verified=True,all_recordings_use_same_roof_radio=all(r["same_radio_as_roof_authority"] for r in rows),
        all_capture_starts_in_declared_roof_interval=all(r["capture_start_within_authority_interval"] for r in rows),
        adaptive_pose_bindings_verified=sum(r["pose_binding_verified"] for r in rows),
        supplied_vs_operator_roof_coordinate_distance_m=distance,
        operator_roof_coordinate_is_not_an_independent_GNSS_survey=True,
        no_motion_sensor_or_survey_altitude_is_provided_by_authority=True,
        fast_recordings_only_have_radio_and_time_eligibility_not_adaptive_pose_binding=True,
        no_reference_coordinates_or_pose_enter_inference=True,
        reference_was_not_changed=True,manifest_sha256="sha256:"+hashlib.sha256(source.read_bytes()).hexdigest(),
        authority_sha256="sha256:"+hashlib.sha256(authority_path.read_bytes()).hexdigest(),
        source_sha256="sha256:"+hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(json.dumps(result,indent=2,allow_nan=False))


if __name__=="__main__":run()
