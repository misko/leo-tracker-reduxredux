"""Freeze existing site-conditioned IDs separately from the blind RF experiment."""

import argparse
import gzip
import json
from pathlib import Path

from replay_regional_doppler import write_json

from leo.storage.scanner_tracking import ScannerTrackingStore


def prepare(evidence, audit, output):
    frozen = json.loads(gzip.decompress(audit.read_bytes()))["sessions"]
    fallback = {
        r["session_id"]: r["tracking"]["product"]
        for r in frozen
        if r.get("tracking", {}).get("product")
    }
    store = ScannerTrackingStore(Path("/srv/bulk/leo"), read_only=True)
    output.mkdir(parents=True, exist_ok=False)
    (output / "evidence").mkdir()
    inventory = json.loads((evidence / "inventory.json").read_text())
    sky = []
    for row in inventory["scans"]:
        if not row["included"]:
            continue
        sid = row["session_id"]
        current = store.status(sid).product
        product = (
            current.model_dump(mode="json")
            if current and current.track_reviews
            else fallback.get(sid)
        )
        if not product:
            row.update(included=False, reason="no existing per-track association review")
            continue
        doc = json.loads((evidence / "evidence" / f"{sid}.json").read_text())
        if doc["inventory"]["capture_digest"] != product["input_manifest_sha256"]:
            raise ValueError("site-conditioned review and RF evidence refer to different captures")
        reviews = {r["tracklet_id"]: r for r in product["track_reviews"]}
        fixed = {}
        for r in doc["series"]:
            review = reviews.get(r["tracklet_id"])
            if not review or len(review["candidates"]) < 2:
                continue
            first, second = review["candidates"][:2]
            # Existing user-requested strong-separation diagnostic, not a new identity proof.
            if (
                max(first["fit_rms_hz"], first["randomized_evaluation_rms_hz"]) < 60
                and second["randomized_evaluation_rms_hz"] > 300
            ):
                fixed[r["tracklet_id"]] = first["catalog_number"]
        for review in product["track_reviews"]:
            if len(review["candidates"]) < 2:
                continue
            a, b = review["candidates"][:2]
            sky.append(
                dict(
                    session_id=sid,
                    sample_rate_hz=row["sample_rate_hz"],
                    reference_utc_ns=doc["inventory"]["reference_utc_ns"],
                    tle_file=doc["inventory"]["tle_file"],
                    observer_site=product["observer_site"],
                    product_version=product["schema_version"],
                    **review,
                )
            )
        doc["series"] = [r for r in doc["series"] if r["tracklet_id"] in fixed]
        doc["episodes"] = [r for r in doc["episodes"] if r["episode_id"] in fixed]
        doc["inventory"]["fixed_candidates"] = fixed
        doc["inventory"]["known_site_candidate_fields_used"] = True
        row.update(included=bool(fixed), episode_count=len(fixed))
        if not fixed:
            row["reason"] = "no representative with top RMS <60 Hz and runner >300 Hz"
            continue
        tle = doc["inventory"]["tle_file"]
        dest = output / "evidence" / tle
        if not dest.exists():
            dest.symlink_to((evidence / "evidence" / tle).resolve())
        write_json(output / "evidence" / f"{sid}.json", doc)
    inventory.update(
        prior_matched_norads_used=True,
        selection_uses_tle_or_known_location=True,
        warning=(
            "This experiment conditions on identities selected using the configured "
            "receiver site; it is not blind geolocation."
        ),
    )
    write_json(output / "inventory.json", inventory)
    write_json(output / "site-conditioned-sky-reviews.json", sky)
    print(
        "fixed tracks",
        sum(r.get("episode_count", 0) for r in inventory["scans"] if r["included"]),
        "sky reviews",
        len(sky),
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for key in ["evidence", "audit", "output"]:
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    prepare(a.evidence, a.audit, a.output)
