"""Freeze a metadata-selected 2 + 16 offline cohort, without reading fit scores.

This research adapter reads explicit published manifest paths from the inventory.
It does not infer IQ paths, mutate capture storage, or claim IQ payload readiness.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
REFERENCES = {"scan-fw-911c4e5db9243281": "A", "scan-fw-ffa1cc19d8d7c09f": "B"}
ROOF = [37.849056280893684, -122.48575489722863]
SEED = "ds13-18scan-20261004-v1"
BLOCK_NS = 3 * 3600 * 10**9
GUARD_NS = 30 * 60 * 10**9


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def verify_capture(wrapper, pose, inventory_rate):
    manifest = wrapper["manifest"]
    authority = pose["pose_authority"]
    geometry = manifest["receipt"]["plan"]["geometry"]
    timing = manifest["timing"]
    start = timing["first_sample_earliest_utc_ns"]
    end = timing["terminal_realtime_ns"]
    checks = {
        "manifest_digest": digest(canonical(manifest)) == wrapper["sha256"],
        "pose_binding_digest": digest(canonical({k: v for k, v in pose.items() if k != "binding_digest"})) == pose["binding_digest"],
        "pose_authority_digest": digest(canonical(authority)) == pose["pose_authority_digest"],
        "session_binding": manifest["session_id"] == pose["session_id"],
        "manifest_binding": pose["manifest_sha256"] == wrapper["sha256"],
        "time_binding": start == pose["capture_start_earliest_utc_ns"] and end == pose["capture_end_utc_ns"],
        "pose_validity": authority["valid_from_utc_ns"] <= start < end < authority["valid_until_utc_ns"],
        "fixture": authority["fixture_part_id"] == "LT3D-004B" and authority["nominal_outward_tilt_deg"] == 20,
        "roof": [authority["latitude_deg"], authority["longitude_deg"]] == ROOF,
        "receivers": sorted(geometry["receiver_ids"]) == [0, 1],
        "receiver_orientation": {r["receiver_id"]: r["azimuth_deg"] for r in authority["receivers"]} == {0: 270, 1: 90},
        "sample_rate": geometry["sample_rate_hz"] == int(inventory_rate),
        "four_channels": {p["target"]["channel"] for p in geometry["profiles"]} == {1, 2, 3, 4},
    }
    failed = [k for k, v in checks.items() if not v]
    if failed:
        raise ValueError("capture validation: " + ", ".join(failed))
    epoch = timing["first_sample_estimate_utc_ns"]
    date = datetime.fromtimestamp(epoch / 1e9, timezone.utc)
    return dict(session_id=manifest["session_id"], sample_rate_hz=geometry["sample_rate_hz"],
                capture_start_ns=epoch, capture_end_ns=end, time_block=epoch // BLOCK_NS,
                capture_utc=date.isoformat(), capture_local=date.astimezone(ZoneInfo("America/Los_Angeles")).isoformat(),
                manifest_sha256=wrapper["sha256"], pose_binding_digest=pose["binding_digest"],
                pose_authority_digest=pose["pose_authority_digest"], metadata_checks=checks,
                iq_readiness="not_checked", analysis_readiness="not_checked",
                tle_readiness="not_checked")


def select_new(rows, references):
    """One scan per 3-hour block; 30-minute separation including A/B.

    Input rows contain metadata only. SHA ordering is deterministic and avoids
    dependence on input traversal order, Python RNG versions, or scientific scores.
    """
    def priority(row):
        return hashlib.sha256((SEED + row["session_id"]).encode()).hexdigest()
    chosen = []
    used_blocks = {r["time_block"] for r in references}
    for row in sorted(rows, key=priority):
        if row["time_block"] in used_blocks:
            continue
        if any(max(row["capture_start_ns"], other["capture_start_ns"]) -
               min(row["capture_end_ns"], other["capture_end_ns"]) < GUARD_NS
               for other in references + chosen):
            continue
        chosen.append(dict(row))
        used_blocks.add(row["time_block"])
        if len(chosen) == 16:
            break
    if len(chosen) != 16:
        raise ValueError(f"only {len(chosen)} independently spaced blocks; do not relax policy silently")
    # Each temporal quartile contributes two development, one validation, one test.
    chosen.sort(key=lambda r: (r["capture_start_ns"], r["session_id"]))
    for offset in range(0, 16, 4):
        quartile = sorted(chosen[offset:offset + 4], key=priority)
        for row, split in zip(quartile, ("development", "development", "validation", "locked_test")):
            row["split"] = split
    for i, row in enumerate(chosen, 1):
        row["label"] = f"N{i:02d}"
    return chosen


def build(inventory, pose_root):
    with inventory.open() as stream:
        inventory_rows = list(csv.DictReader(stream))
    eligible, references, exclusions = [], [], []
    prior_bundles = sorted(ROOT.glob("reports/*/scans/*/bundle.json"))
    prior_localization = {path.parent.name for path in prior_bundles}
    for inv in inventory_rows:
        sid = inv["session_id"]
        if sid not in REFERENCES and int(inv["sample_rate_hz"]) != 2_500_000:
            continue
        if sid not in REFERENCES and sid in prior_localization:
            exclusions.append(dict(session_id=sid, reason="prior localization bundle; not a new evaluation scan"))
            continue
        pose_path = pose_root / (sid + ".json")
        try:
            raw_pose = pose_path.read_bytes()
            manifest_path = Path(inv["path"])
            raw_manifest = manifest_path.read_bytes()
            row = verify_capture(json.loads(raw_manifest), json.loads(raw_pose), inv["sample_rate_hz"])
            row.update(manifest_path=str(manifest_path), manifest_file_sha256=digest(raw_manifest),
                       pose_path=str(pose_path), pose_file_sha256=digest(raw_pose))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            exclusions.append(dict(session_id=sid, reason=f"{type(exc).__name__}: {exc}"))
            continue
        if sid in REFERENCES:
            references.append(dict(row, label=REFERENCES[sid], split="reference"))
        else:
            eligible.append(row)
    if {r["session_id"] for r in references} != set(REFERENCES):
        raise ValueError("A/B reference verification failed")
    if len({r["session_id"] for r in eligible}) != len(eligible):
        raise ValueError("duplicate inventory sessions")
    selected = sorted(references, key=lambda r: r["label"]) + select_new(eligible, references)
    return dict(schema="offline-18scan-cohort/v1", status="metadata_frozen_payload_preflight_pending",
                seed=SEED, selection="Deterministic metadata-only SHA order; one scan per three-hour UTC block; 30-minute interval guard including A/B; splits balanced across temporal quartiles.",
                inventory_path=str(inventory), inventory_sha256=digest(inventory.read_bytes()),
                prior_localization_bundles=[str(p) for p in prior_bundles],
                supersedes_metadata_draft="cohort.json (not used for inference; previously localized scan found before test lock)",
                implementation_sha256=digest(Path(__file__).read_bytes()),
                known_roof_lat_lon=ROOF, coordinate_authority="Capture-bound operator coordinates; not surveyed; altitude unknown.",
                interpretation="A/B are reference scans at their original rates. Sixteen additions are 2.5 MS/s with LT3D-004B capture bindings. Extended fixture cohort, not a redefinition of the historical DS13 dataset.",
                eligible_new_count=len(eligible), eligible_new=eligible, exclusions=exclusions,
                scans=selected, splits=dict(Counter(r["split"] for r in selected)),
                leakage_caveat="Historical sample-rate audit exposed aggregate tracking metrics. No localization outcomes are consulted for selection; previously unknown does not mean never processed. Same site/hardware throughout.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=ROOT / "reports/2026_10_03_sample_rate_rms/recordings.csv")
    parser.add_argument("--pose-root", type=Path, default=Path("/srv/bulk/leo/capture-pose/gauss-r20-lt3d-004b-20261001-v1"))
    parser.add_argument("--output", type=Path, default=OUT / "cohort-v2.json")
    args = parser.parse_args()
    result = build(args.inventory, args.pose_root)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(eligible=result["eligible_new_count"], splits=result["splits"],
                          selected=[{k: r[k] for k in ("label", "session_id", "sample_rate_hz", "capture_local", "split")} for r in result["scans"]]), indent=2))


if __name__ == "__main__":
    main()
