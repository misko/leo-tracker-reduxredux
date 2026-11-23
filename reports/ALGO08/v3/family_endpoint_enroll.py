"""Enroll one named physical saved case by input availability and issued visits."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROSTER = Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac")
LOCAL = Path("/tmp/ds30-v2-stage-all-6cdbac")
BINDINGS = Path("/srv/bulk/leo-dev/ds30-full-20261121/bindings")
PINS = {"panel.json": "147886973a6419baa925263c02e7b8d37e13737c94518bba69a023f47389d399",
        "final/decision.json": "26ac73f584b58150b1205ccfb848b0317af322d5389c0b4e8eaf18c0a178f1f1"}
EXCLUDED = frozenset({"DS30-0402", "DS30-0160", "DS30-0316", "DS30-0155", "DS30-0057", "DS30-0016", "DS30-0008"})
CAP = 90_000_000
STOCK = "sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f"
DETECTOR = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"


def digest(data):
    return sha256(data).hexdigest()


def verified(path, pin):
    result = path.read_bytes()
    if digest(result) != pin.removeprefix("sha256:"):
        raise ValueError(f"Unverified saved input {path}")
    return result


def priority(cases):
    band = sorted((abs(count-3750), label) for label, count in cases.items()
                  if 1500 <= count <= 6000 and label not in EXCLUDED)
    fallback = sorted((count, label) for label, count in cases.items()
                      if not 1500 <= count <= 6000 and count > 0 and label not in EXCLUDED)
    return [label for _, label in band], [label for _, label in fallback]


def available(label, path, pin, pair, expected):
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader

    old = pair["runs"]["candidate"]
    rec = old["receipt"]
    root = path.parent / "candidate/fast-scan-automatic-work"
    packet = list(root.glob("*/detections.json"))
    terminal = root / rec["run_id"] / "terminal.json"
    inventory = root.parent / "fast-scan-inputs" / f"{rec['session_id']}.json"
    case_binding = BINDINGS / f"{label}.json"
    offer = Path(pair["region"])
    if len(packet) != 1 or any(not p.is_file() or p.stat().st_size <= 0 for p in (*packet, terminal, inventory, case_binding, offer)):
        return None, "missing saved packet, terminal, inventory, binding or offer"
    archive = pair["archive"]
    if not Path(archive["root"]).is_dir():
        return None, "missing causal archive"
    snapshots = TleArchiveReader(Path(archive["root"])).list_snapshots("space-track")
    bytes_total = sum(r.byte_size for r in snapshots)
    if not 0 < bytes_total <= CAP:
        return None, "causal archive exceeds the cap or is empty"
    raw_binding = case_binding.read_bytes()
    assigned = json.loads(raw_binding)
    authority, cutoff = assigned["case"], assigned["orbit_cutoff_ns"]
    if (canonical_digest({r.path.name: r.sha256 for r in snapshots}) != expected["archive_digest"]
            or archive["snapshots_sha256"] != expected["archive_digest"] or any(r.collected_utc_ns >= cutoff for r in snapshots)
            or authority["id"] != label or authority["raw_authority"] != expected["raw_authority"]
            or authority["session_id"] != rec["session_id"] or rec["session_id"] != expected["session"]
            or old["raw_authority"] != expected["raw_authority"] or rec["region"] != expected["region"]):
        return None, "signed archive, authority, region or cutoff differs"
    return dict(case=label, issued=rec["window_count"], admitted=rec["counts"]["processed"], pair=str(path), pair_sha256=pin,
                named_decision=rec["decision"], packet=str(packet[0]), inventory=str(inventory), offer=str(offer),
                terminal=str(terminal), terminal_sha256=rec["terminal_sha256"], original_archive=archive,
                archive_bytes=bytes_total, snapshots=len(snapshots), binding_sha256=digest(raw_binding),
                cutoff_utc_ns=cutoff, recording=pair["recording"], session=rec["session_id"], authority=expected["raw_authority"]), None


def select():
    panel = {r["case"]: r for r in json.loads(verified(ROSTER/"panel.json", PINS["panel.json"]))["cases"]}
    pins = json.loads(verified(ROSTER/"final/decision.json", PINS["final/decision.json"]))["pair_sha256"]
    if len(panel) != 100 or set(panel) != set(pins):
        raise ValueError("Named-v3 roster assignments disagree")
    inventory, unavailable = {}, {}
    for label, pin in pins.items():
        path = LOCAL / label / "pair.json"
        if not path.is_file():
            unavailable[label] = "missing local signed pair"
            continue
        pair = json.loads(verified(path, pin))
        named = pair["runs"]["candidate"]
        receipt = named.get("receipt") or {}
        if (pair["candidate_specification_digest"] != STOCK or pair["candidate_specification"]["detector_sha256"] != DETECTOR
                or receipt.get("decision") not in ("complete", "withheld") or type(receipt.get("window_count")) is not int):
            unavailable[label] = "no complete selected named receipt"
            continue
        inventory[label] = path, pin, pair, receipt["window_count"]
    counts = {label: row[-1] for label,row in inventory.items()}
    band, fallback = priority(counts)
    rejected = []
    for label in (*band, *fallback):
        path, pin, pair, _ = inventory[label]
        selected, reason = available(label, path, pin, pair, panel[label])
        if selected is not None:
            return dict(selected=selected, examined=rejected, band=[(name, counts[name]) for name in band],
                        fallback=label not in band, excluded=sorted(EXCLUDED), local_receipts=len(inventory),
                        other_sources_unavailable=unavailable, roster_pins=PINS, protocol_sha256=digest(
                            (HERE/"family-endpoint-transfer-protocol.md").read_bytes()))
        rejected.append(dict(case=label, issued=counts[label], reason=reason))
    raise ValueError("No case satisfies the frozen signed saved-input availability rule")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = select()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True)
        stream.write("\n")
