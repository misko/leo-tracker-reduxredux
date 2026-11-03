"""Read-only capture-pose audit; emits a small, reproducible evidence receipt."""
import datetime
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).with_name("orientation-evidence.json")
RADIUS_M = 6371008.8  # Identical spherical map convention to the profile test.


def sha(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def inverse(origin, target):
    a, b = map(math.radians, origin)
    c, d = map(math.radians, target)
    angle = 2 * math.asin(math.sqrt(math.sin((c-a)/2)**2 + math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2))
    bearing = math.atan2(math.sin(d-b)*math.cos(c), math.cos(a)*math.sin(c)-math.sin(a)*math.cos(c)*math.cos(d-b))
    return dict(distance_m=RADIUS_M*angle, east_m=RADIUS_M*angle*math.sin(bearing), north_m=RADIUS_M*angle*math.cos(bearing))


def destination(origin, east_m, north_m):
    a, b = map(math.radians, origin)
    angle = math.hypot(east_m, north_m)/RADIUS_M
    bearing = math.atan2(east_m, north_m)
    c = math.asin(math.sin(a)*math.cos(angle)+math.cos(a)*math.sin(angle)*math.cos(bearing))
    d = b + math.atan2(math.sin(bearing)*math.sin(angle)*math.cos(a), math.cos(angle)-math.sin(a)*math.sin(c))
    return list(map(math.degrees, [c, d]))


def utc(ns):
    return datetime.datetime.fromtimestamp(ns//1000000000, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{ns%1000000000:09d}Z"


def run():
    old = ROOT / "reports/2026_10_02_ds13_timing_em/prior-position-audit/pointing-evidence.json"
    previous = json.loads(old.read_text())
    manifest_root = ROOT / "reports/2026_10_02_ds13_from_911c4e5d/local"
    captures = json.loads((manifest_root / "manifest.json").read_text())["captures"]
    records = []
    for row in previous["captures"]:
        path = Path(row["path"])
        raw = path.read_bytes()
        pose = json.loads(raw)
        authority = pose["pose_authority"]
        session = pose["session_id"]
        manifest_path = manifest_root / "published" / (session + ".json")
        manifest = json.loads(manifest_path.read_text())
        capture = next(c for c in captures if c["session_id"] == session)
        checks = dict(source_matches_previous_audit=sha(raw) == row["sha256"],
            binding_digest_valid=pose["binding_digest"] == sha(canonical({k:v for k,v in pose.items() if k != "binding_digest"})),
            authority_digest_valid=pose["pose_authority_digest"] == sha(canonical(authority)),
            manifest_digest_matches_population=pose["manifest_sha256"] == capture["manifest_sha256"],
            start_matches_manifest=pose["capture_start_earliest_utc_ns"] == manifest["timing"]["first_sample_earliest_utc_ns"],
            end_matches_manifest=pose["capture_end_utc_ns"] == manifest["timing"]["terminal_realtime_ns"],
            pose_valid_for_capture=authority["valid_from_utc_ns"] <= pose["capture_start_earliest_utc_ns"] < pose["capture_end_utc_ns"] < authority["valid_until_utc_ns"])
        assert all(checks.values())
        records.append(dict(scan=row["scan"], session_id=session, source_path=str(path), source_sha256=sha(raw),
            manifest_path=str(manifest_path), binding_checks=checks, pose=pose,
            capture_start_earliest_utc=utc(pose["capture_start_earliest_utc_ns"]),
            first_sample_estimate_utc=utc(manifest["timing"]["first_sample_estimate_utc_ns"]),
            capture_end_utc=utc(pose["capture_end_utc_ns"])))
    roof = [authority["latitude_deg"], authority["longitude_deg"]]
    reference = [37.858988, -122.478103]
    summary_path = ROOT / "reports/2026_10_04_ds13_independent_top_response_position/independent-summary.json"
    summary = json.loads(summary_path.read_text())
    comparisons = []
    for case in summary["cases"]:
        latlon = destination(reference, case["east_m"], case["north_m"])
        comparisons.append(dict(scan=case["scan"], arm=case["arm"], minimum_lat_lon=latlon,
            minimum_relative_profile_reference_m=dict(east_m=case["east_m"], north_m=case["north_m"]),
            minimum_relative_operator_roof_m=inverse(roof, latlon),
            note="Re-expresses the prior result only; no score evaluation or search recentering."))
    sources = [old, summary_path, Path(__file__), ROOT/"src/leo/sky/sites.py", ROOT/"docs/operations/radio20-roof-pose-20260926.md",
        ROOT/"docs/operations/radio20-lt3d-004b-20261001.md", ROOT/"deploy/station/gauss-r20-lt3d-004b-20261001-v1.json",
        ROOT/"reports/2026_10_02_multiscan_localization/joint_inputs.py", ROOT/"reports/2026_10_02_multiscan_localization/prediction_jacobian.py"]
    result = dict(captures=records, nominal_axes_enu={"RX0": [-math.sin(math.radians(20)), 0., math.cos(math.radians(20))],
        "RX1": [math.sin(math.radians(20)), 0., math.cos(math.radians(20))]},
        nominal_axis_assumptions="Level mount; geographic azimuth RX0=270deg, RX1=90deg; elevation70deg. 40deg is included feed-axis angle, not azimuth separation and not beam width.",
        measured_beam_width_deg=None, measured_boresights=False, connector_mapping_status="provisional",
        operator_roof_lat_lon=roof, operator_roof_authority="Operator-supplied capture-bound location, WGS84 assumed; altitude and survey uncertainty unknown. Not a surveyed ground truth claim.",
        profile_reference_lat_lon=reference, profile_reference_authority="Spinnaker restaurant OSM display preset; src/leo/sky/sites.py explicitly says presets are never scientific authority. Previous position analysis mislabeled this reference as known roof.",
        operator_roof_relative_profile_reference_m=inverse(reference, roof),
        distance_convention="Spherical geodesic radius6371008.8m, same as previous position-profile coordinate map.",
        prior_minima_reexpressed=comparisons, geometry_altitude_used_m=0.,
        geometry_altitude_scope="joint_inputs._ecef uses WGS84 ellipsoid at h=0m. Actual capture altitude unknown; do not substitute Spinnaker preset altitude -29m.",
        direction_method="Interpolate the saved ECEF-km satellite bank linearly at receive_time + fitted satellite time shift; subtract WGS84 observer ECEF; normalize. ENU dot products give az=atan2(E,N) mod360, el=asin(U). Off-axis=acos(direction dot nominalaxis). E>0 means east; E<0 west.",
        interpretation="Opposite hemisphere is not an impossible association: directions are nominal, lobes overlap, beam patterns unmeasured. Missing assigned track on peer RX is not proof of raw-signal nondetection. Nominal nearer receiver can be reported without a hard exclusion.",
        sources_sha256={str(p):sha(p.read_bytes()) for p in sources})
    OUT.write_text(json.dumps(result, indent=2, allow_nan=False)+"\n")
    print(json.dumps(dict(roof_offset=result["operator_roof_relative_profile_reference_m"], minima=comparisons), indent=2))


if __name__ == "__main__":
    run()
