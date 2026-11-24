"""Transfer the frozen arrival census to the first sealed DS30-0010 pair."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from .anchor_arrival_authority import inventory, score
from .anchor_only_history import ARMS, paired, read, seal, slot
from .directed_donor import ADC


SOURCE_PINS = {
    "pair.json": "5352551fef1d03855fdffc6c713741969aba2a1c5a1e1f21e7d9621e34495ccc",
    "authority.json": "b94beeb503747e47c08bc4674b5b7ff907f756865ba8fb84bb3fb30ff36d70ba",
    "publication-held-anchor-route.json": "2eb0991587bd5818a7d9a91bd585c3c168849399e4ab48b5118effdb29b22784",
    "exact-named-raw-witness.json": "a06684b304d71f1c8567b09da37bb9515a5240dd949fb42f13c0782023ae89f7",
    "unified-short-bootstrap.json": "d95773e99f002e5e80fd6e7f5c91f317b354b0a9bec3357d54b4f2ab9e207f88",
}
ARM_PINS = {
    "installed": {
        "result.json": "1b0915cb65d4eacceb1dd76e359df66446a78b257ffe771386f866407bc11549",
        "detections.json": "f9d04b443b0d18195a5deaa0c2689a086741c7f0b2d032fd16d4772f8638c2bf",
        "manifest.json": "e32848c4b5a9f52a311cf7ce2c368a93b08af202c3dd80347a407a99ee043e4c",
    },
    "successor": {
        "result.json": "f53da50f9cdb95483560824b9d78b2a3a9fb5f033ce25f2407fe9751108b5063",
        "detections.json": "f212387fe6a24ecf862fa9eca1f6752684c792493f4e643c4bc849d1b92af502",
        "manifest.json": "408d42328d7a8415c1ff91dc0897ddea48c207b20aad223cd464349c1ef07a27",
    },
}


def qualified_inputs(case):
    pair, authority = (read(case / name, SOURCE_PINS[name]) for name in ("pair.json", "authority.json"))
    attempts, packets, manifests = {}, {}, {}
    expected = {arm: "sha256:" + pins["result.json"] for arm, pins in ARM_PINS.items()}
    if (pair["verified_pair"] is not True or pair["state"] != "observed_pair" or not pair["chronological"]
            or pair["generation"] != 1 or pair["actual_order"] != ["installed", "successor"]
            or pair["attempt_result_sha256"] != expected or pair["authority_sha256"] != "sha256:" + SOURCE_PINS["authority.json"]):
        raise ValueError("The pre-enrolled complete pair differs")
    for arm, pins in ARM_PINS.items():
        root = case / arm / "attempt-000001"
        published = root / "publication"
        native, = published.glob("fast-scan-automatic-work/*/detections.json")
        manifest, = published.glob("fast-scan-standard-v2/*/*/manifest.json")
        attempts[arm] = result = read(root / "result.json", pins["result.json"])
        packets[arm] = packet = read(native, pins["detections.json"])
        manifests[arm] = detail = read(manifest, pins["manifest.json"])
        source = packet["source"]
        if (result["outcome"] != "complete" or result["algorithm"] != arm or result["raw_identity"] != authority
                or result["native_sha256"] != "sha256:" + pins["detections.json"] or detail["input_sha256"] != result["native_sha256"]
                or source["qualified"] is not True or source["sample_rate_hz"] != ADC
                or source["session_id"] != authority["session_id"] or source["input_manifest_sha256"] != authority["inventory_sha256"]
                or source["raw_recording_authority_digest"] != authority["raw_authority_sha256"]
                or packet["provenance"]["window_count"] != authority["window_count"]
                or {a: detail["arms"][a]["owner_sha256"] for a in ARMS} != result["evidence"]["owners"]):
            raise ValueError("Attempt, detector, and published evidence do not share original authority")
    return pair, authority, attempts, packets, manifests


def verified_owners(rows, hashes, positive_ids, counts):
    ownership = {}
    for arm in ARMS:
        values = {uid: norad for uid, norad, _ in rows[arm]}
        if (len(values) != len(rows[arm]) or len(values) != counts[arm]
                or not values.keys() <= positive_ids or "sha256:" + seal(values) != hashes[arm]):
            raise ValueError("Exact archived owner rows do not reproduce the official owner digest")
        ownership[arm] = set(values)
    return ownership


def owner_scope(native, stock, measured, ids):
    positive = {slot(row) for row in stock if row["candidates"]}
    session = native["source"]["session_id"]
    anchors = {id_for(session, row["slot"][1], row["counter"]): row for row in measured["anchors"]}
    counts = {}
    for arm, owners in ids.items():
        full = [row for oid, row in anchors.items() if oid in owners]
        extras = [row for row in full if row["slot"] not in positive]
        counts[arm] = dict(all_owned=len(owners), full_owned=len(full), short_owned=len(owners)-len(full),
                           full_owned_with_peer=sum(row["peer"] is not None for row in full), extra_owned=len(extras),
                           extra_owned_with_peer=sum(row["peer"] is not None for row in extras),
                           extra_owned_with_two_short_donors=sum(row["short_before"]+row["short_after"] >= 2 for row in extras))
    return counts


def id_for(session, radio, counter):
    return "sha256:" + sha256(f"{session}:{radio}:{counter}".encode()).hexdigest()


def run(case):
    pair, authority, attempts, packets, manifests = qualified_inputs(case)
    mixed = packets["successor"]
    root = case / "successor/attempt-000001"
    route = read(root / "publication-held-anchor-route.json", SOURCE_PINS["publication-held-anchor-route.json"])
    boot = read(root / "publication/unified-short-bootstrap.json", SOURCE_PINS["unified-short-bootstrap.json"])
    native = boot["receiver_audit"]["native"]
    if (route["choice"]["route"] != "unfiltered" or route["refinement_calls"] != 0
            or route["native_sha256"] != boot["native_sha256"] or route["native_sha256"] != attempts["successor"]["native_sha256"]
            or native["rule"] != ["full"] + ["short_primary"] * 7
            or packets["installed"]["provenance"]["detector_sha256"] != "sha256:" + native["installed_sha256"]):
        raise ValueError("The realized pair does not implement the frozen receiver schedule")
    observed = inventory(mixed["source"]["probes"])
    observation_sha256 = seal(observed)
    full, candidate = paired(packets["installed"], mixed)
    counts = Counter("positive" if row["candidates"] else "empty" for row in candidate)
    lanes = observed["full_anchor_lanes"]
    if (native["native_calls"] != {"full": lanes, "short_primary": len(candidate)-lanes}
            or native["factors"] != {"full": len(observed["anchors"]), "short_primary": counts["positive"]-len(observed["anchors"])}):
        raise ValueError("Reconstructed chronology differs from the authenticated callback schedule")
    witness = read(root / "publication/exact-named-raw-witness.json", SOURCE_PINS["exact-named-raw-witness.json"])["evidence"]
    official = {arm: {a: docs["arms"][a]["associated_points"] for a in ARMS} for arm, docs in manifests.items()}
    if witness["detail"]["input_sha256"] != attempts["successor"]["native_sha256"]:
        raise ValueError("The order of archived owners does not belong to the sealed detector")
    ids = {id_for(authority["session_id"], row["receiver_id"], row["valid_start_counter"]) for row in candidate if row["candidates"]}
    owners = verified_owners(witness["owner_rows"], attempts["successor"]["evidence"]["owners"], ids, official["successor"])
    evidence = score(observed, full, authority["session_id"], {arm: set() for arm in ARMS}, owners)
    return dict(case="DS30-0010", pairs_verified=pair["verified_pair"], observables_sha256=observation_sha256,
                sources=SOURCE_PINS, attempts=ARM_PINS, issued=authority["window_count"], callback_counts=native["native_calls"],
                timing_present=mixed["source"]["timing"] is not None, exact_owner_rows={"installed": False, "successor": True},
                official_owned_counts=official, successor_owner_scope=owner_scope(mixed, full, observed, owners),
                arrival=evidence, waveform_opens=0, catalogue_opens=0, native_calls=0, solver_calls=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path)
    print(json.dumps(run(parser.parse_args().case), sort_keys=True, indent=2, allow_nan=False))
