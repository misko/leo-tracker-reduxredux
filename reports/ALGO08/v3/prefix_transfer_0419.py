"""Audit the first signed DS30-0419 member against the full saved owners."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import isfinite
from pathlib import Path
from statistics import median
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
BASE = Path("/dev/shm/leo-v3-nomination-handoff-0419-local01")
PINS = {
    "admission.json": "ef2f3b0367b94b998b7b1eea3d59b925f104b51067e947410241f3f0ffe6a343",
    "prediction-seal.json": "ecee2159f614d83d89ec38b967507b76ea2652e5ec12f98e315a4696bc03de91",
    "job.json": "23c1e2d851323038a849efbe11f65f541a0f004f370bd4c0534e937f38f237d6",
    "request.json": "333faaee6e48085385db617e6422c08d58aed3c99baa74c9119cd3fc09dd7614",
    "native.json": "50c4ca874573d6e7abb3590e0be9f8099fa87ce7529120d362666dd6a872a5e9",
    "inventory.json": "bc869c479a0e5c0d4fc4e7b1b19032d3e131c4f741c4910317e8cede3e133256",
    "result.json": "0e2bec8d6b8083976c9f0491dc65599d32a2c159e2a3d162eb3d9d4bc7dee7e9",
    "installed/candidate/joint-research-receipt.json": "55a586cae982587e7227a498ebfe48174093d7dc1a0db5d4d32f6d547b00c47a",
    "routed/candidate/joint-research-receipt.json": "c3c0500afff933d7598bb76027e9ba75850f8d3122d43c6fe57f3221ca05338d",
}
MEMBER_VISITS = 64
ARMS = ("c0", "fitted_c")
MODES = ("installed", "routed")
RADIOS = (0, 1)
CFO = "fractional_tracking_cfo_hz"
EPOCH = "integer_epoch_sample"
OFFSET = "fractional_epoch_offset_samples"
RANK = "candidate_rank"
GATE = "passed_fractional_margin_gate"
SCORES = ("fractional_exact_score", "fractional_control_score", "fractional_margin")
ROW_FIELDS = (CFO, EPOCH, OFFSET, RANK, GATE, *SCORES)
SOURCE_IDENTITY = ("capture_mode", "sample_rate_hz", "radio_id", "stream_generation", "probe_ms", "timing")


def checked(path, expected):
    mount = next((p for p in map(Path, ("/dev/shm", "/tmp")) if path.is_relative_to(p)), None)
    if mount is None or path.resolve(strict=True) != path or path.stat().st_dev != mount.stat().st_dev:
        raise ValueError(f"Expected direct RAM staging for {path}")
    body = path.read_bytes()
    if sha256(body).hexdigest() != expected.removeprefix("sha256:"):
        raise ValueError(f"Staged digest changed for {path}")
    return body


def read(path):
    return json.loads(path.read_bytes())


def write(path, data):
    with path.open("x") as stream:
        json.dump(data, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def lane_key(row):
    return row["visit_index"], row["receiver_id"]


def observation_id(session, row):
    return "sha256:" + sha256(f'{session}:{row["receiver_id"]}:{row["valid_start_counter"]}'.encode()).hexdigest()


def metadata(row):
    return {k: v for k, v in row.items() if k != "candidates"}


def lane_rows(packet, visits):
    lanes = {}
    for row in packet["source"]["probes"]:
        visit, radio = lane_key(row)
        if (type(visit) is not int or not 0 <= visit < visits or type(radio) is not int or radio not in RADIOS
                or (visit, radio) in lanes or type(row["valid_start_counter"]) is not int):
            raise ValueError("Invalid or duplicate chronological lane")
        ranks = set()
        for factor in row["candidates"]:
            if (set(factor) != set(ROW_FIELDS) or type(factor[GATE]) is not bool
                    or type(factor[EPOCH]) is not int or type(factor[RANK]) is not int or factor[RANK] in ranks
                    or not all(isfinite(factor[k]) for k in (CFO, OFFSET, *SCORES))):
                raise ValueError("Invalid signed native factor")
            ranks.add(factor[RANK])
        lanes[visit, radio] = row
    excluded = {row["visit"]: row for row in packet["provenance"]["excluded_windows"]}
    admitted = {i for i in range(visits) if (i, 0) in lanes}
    if (len(excluded) != len(packet["provenance"]["excluded_windows"]) or set(excluded) & admitted
            or set(excluded) | admitted != set(range(visits)) or set(lanes) != {(i, radio) for i in admitted for radio in RADIOS}
            or (packet["provenance"]["window_count"], packet["provenance"]["processed_windows"], packet["provenance"]["invalid_capture"])
            != (visits, len(admitted), len(excluded)) or len(packet["delivery_clocks"]) != visits):
        raise ValueError("Lost original visit coverage, stereo lanes, or excluded-window evidence")
    return lanes, excluded


def prefix_scope(full, stock, mixed, witness):
    """Bind each apparent detector lane to the original absolute issued visit."""
    archive_lanes, archive_excluded = lane_rows(full, full["provenance"]["window_count"])
    payload = witness["visits"]
    if (len(payload) != MEMBER_VISITS or [x["sequence"] for x in payload] != list(range(MEMBER_VISITS))
            or any(x["sample_end"] <= x["sample_start"] for x in payload)
            or full["clock_anchor"]["sample_counter"] != payload[0]["sample_start"]):
        raise ValueError("The signed member does not witness the entire original first 64 visits")
    views = {"archived": ({k: r for k, r in archive_lanes.items() if k[0] < MEMBER_VISITS},
                           {k: r for k, r in archive_excluded.items() if k < MEMBER_VISITS})}
    for name, native in (("installed_prefix", stock), ("mixed_prefix", mixed)):
        if (native["clock_anchor"] != full["clock_anchor"] or native["last_sample_counter"] != payload[-1]["sample_end"]
                or native["delivery_clocks"] != full["delivery_clocks"][:MEMBER_VISITS]
                or any(native["source"][k] != full["source"][k] for k in SOURCE_IDENTITY)):
            raise ValueError(f"The original clock, signed RF epoch or receiver convention changed in {name}")
        views[name] = lane_rows(native, MEMBER_VISITS)
    for lanes, exclusions in views.values():
        for row in payload:
            visit = row["sequence"]
            if visit in exclusions:
                actual = exclusions[visit]
                if any(actual[name] != row[name] for name in ("sample_start", "sample_end", "iq_sha256")):
                    raise ValueError("An excluded native visit does not match its signed counter interval or IQ hash")
                continue
            for radio in RADIOS:
                native = lanes[visit, radio]
                if (native["valid_start_counter"] != row["sample_start"]
                        or any(native[name] != row[name] for name in ("channel", "actual_rf_hz", "edge"))):
                    raise ValueError("Native lane coordinate, RF or side disagrees with the signed visit")
    return views, archive_lanes


def signed_member(stage, inventory):
    """Read only the two small staged files committed by the original member."""
    first = inventory["segments"][0]
    if stage.name != Path(first["path"]).name or first["scope"] != "segment-00000000":
        raise ValueError("The stage is not the original first segment")
    manifest = json.loads(checked(stage / "manifest.json", first["manifest_digest"]))
    member = manifest["chunks"][0]
    if (manifest["window_count"] != first["windows"] or manifest["receiver_ids"] != list(RADIOS)
            or manifest["sample_rate_hz"] != 10_000_000 or (member["chunk_index"], member["first_sequence"],
            member["window_count"]) != (0, 0, MEMBER_VISITS)):
        raise ValueError("The original signed member does not cover exactly the prescribed 64 visits")
    filename = member["index_relative_path"]
    if Path(filename).name != filename or not filename.endswith(".jsonl"):
        raise ValueError("Need a direct signed index file")
    body = checked(stage / filename, member["index_sha256"])
    targets = {row["target_id"]: row for row in manifest["configuration"]["targets"]}
    visits, offset = [], 0
    for sequence, line in enumerate(body.splitlines()):
        row = json.loads(line)
        a, target = row["acquisition"], targets[row["target_id"]]
        start, end = a["sample_start"], a["sample_end"]
        retune = json.loads(a["retune_receipt"])
        if (row["sequence"] != sequence or a["global_visit"] != sequence or a["counter_authority"] != "hardware"
                or row["payload_offset_bytes"] != offset or row["receiver_count"] != len(RADIOS)
                or row["payload_bytes"] != 4 * len(RADIOS) * row["sample_count"]
                or end - start != row["sample_count"] or (visits and start < visits[-1]["sample_end"])
                or not row["iq_sha256"].startswith("sha256:") or len(row["iq_sha256"]) != 71):
            raise ValueError("The signed index has incorrect original hardware support")
        offset += row["payload_bytes"]
        visits.append(dict(sequence=sequence, sample_start=start, sample_end=end, iq_sha256=row["iq_sha256"],
                           clock=retune["host_delivery_clock"], clock_anchor=retune.get("utc_clock_bracket"),
                           channel=target["channel"], actual_rf_hz=target["rf_center_hz"], edge=target["edge"]))
    if (len(body), len(visits), offset) != (member["index_bytes"], MEMBER_VISITS, member["uncompressed_bytes"]):
        raise ValueError("The index does not prove the complete signed first member")
    return dict(segment=first, member=member, visits=visits, serial=manifest["radio"]["serial"])


def verified_owner_rows(rows, digests, allowed, digest):
    by_arm = {}
    if set(rows) != set(ARMS) or set(digests) != set(ARMS):
        raise ValueError("Owner rows must bind both calibrated arms")
    for arm in ARMS:
        roster = {obs: [norad, role] for obs, norad, role in rows[arm]}
        if (len(roster) != len(rows[arm]) or not roster.keys() <= allowed
                or digest({obs: value[0] for obs, value in roster.items()}) != digests[arm]):
            raise ValueError("The ordered conditional/supporting roster does not bind the published observation IDs")
        by_arm[arm] = roster
    return by_arm


def archived():
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest

    docs = {name: json.loads(checked(BASE / name, pin)) for name, pin in PINS.items()}
    native, request, inventory = (docs[name + ".json"] for name in ("native", "request", "inventory"))
    if (request["case"] != "DS30-0419" or (request["issued"], request["admitted"]) != (6774, 5220)
            or inventory["window_count"] != request["issued"] or native["source"]["raw_recording_authority_digest"] != request["raw_authority"]
            or request["native_sha256"] != PINS["native.json"] or request["inventory"] != "sha256:" + PINS["inventory.json"]):
        raise ValueError("The original full packet enrollment or scope changed")
    bind_native(native, request["session"], request["inventory"], native["provenance"]["detector_sha256"][7:],
                expected="sha256:" + PINS["native.json"])
    lanes, excluded = lane_rows(native, request["issued"])
    allowed = {observation_id(request["session"], row) for row in lanes.values() if row["candidates"]}
    owners, trials = {}, {}
    result = docs["result.json"]
    if result["prediction_seal_sha256"] != PINS["prediction-seal.json"]:
        raise ValueError("The prior geographic and publication scorer lost its original prediction binding")
    for mode in MODES:
        name = f"{mode}/clock.json"
        clock = json.loads(checked(BASE / name, docs["prediction-seal.json"][name]))
        prior = result["jobs"][mode]
        run = prior["publication"]
        traces = docs[f"{mode}/candidate/joint-research-receipt.json"]
        terminal, science = run["terminal"], run["science"]
        if (clock["exit_code"] != 0 or prior["clock"] != clock or prior["decision"] != "complete"
                or run["selected_rows"] != traces["selected_rows"] or terminal["decision"] != "ok"
                or terminal["native_sha256"] != "sha256:" + PINS["native.json"]
                or terminal["session_id"] != request["session"] or science["raw_authority"] != request["raw_authority"]
                or canonical_digest(terminal) != traces["receipt"]["terminal_sha256"] or len(run["figures"]) != 8):
            raise ValueError("The full-recording publication no longer verifies")
        owners[mode] = verified_owner_rows(run["selected_rows"], science["owners"], allowed, canonical_digest)
        trials[mode] = dict(clocks=clock, terminal=terminal, figures=run["figures"],
                            scientific_digests=science["scientific_digests"], sample_count=traces["solve"]["grid_points"])
    return docs, lanes, excluded, owners, trials


def archive_prefix(stage, docs, lanes, excluded, owners):
    full, inventory = docs["native.json"], docs["inventory.json"]
    witness = signed_member(stage, inventory)
    # The archive is validated against the actual signed metadata without claiming a prefix detector replay.
    original_prefix = dict(full, source=dict(full["source"], probes=[r for k, r in lanes.items() if k[0] < MEMBER_VISITS]),
                           delivery_clocks=full["delivery_clocks"][:MEMBER_VISITS], last_sample_counter=witness["visits"][-1]["sample_end"])
    skipped = [row for k, row in excluded.items() if k < MEMBER_VISITS]
    original_prefix["provenance"] = dict(full["provenance"], window_count=MEMBER_VISITS,
         processed_windows=MEMBER_VISITS - len(skipped), invalid_capture=len(skipped), excluded_windows=skipped)
    if (witness["serial"] != full["source"]["radio_id"] or full["clock_anchor"] != witness["visits"][0]["clock_anchor"]
            or full["delivery_clocks"][:MEMBER_VISITS] != [visit["clock"] for visit in witness["visits"]]):
        raise ValueError("The original radio or absolute clock binding changed")
    data, _ = overlap(full, original_prefix, original_prefix, witness, owners)
    return witness, dict(coverage=data["owner_counts"], excluded_visits=sorted(row["visit"] for row in skipped),
         admitted_visits=MEMBER_VISITS - len(skipped), positive_lanes=sum(bool(row["archived_factors"]) for row in data["lanes"]),
         native_factors=sum(len(row["archived_factors"]) for row in data["lanes"]),
         factor_rows=[{k: row[k] for k in ("visit", "receiver", "channel", "original_observation_id", "owners", "archived_factors")}
                      for row in data["lanes"] if row["archived_factors"]])


def factor_contrast(before, after):
    """Pair only unambiguous single factors and exact equal multiple rows."""
    if not before or not after:
        return dict(lost=before, gained=after, retained=[], ambiguous_before=[], ambiguous_after=[])
    if len(before) == len(after) == 1:
        a, b = before[0], after[0]
        return dict(lost=[], gained=[], retained=[dict(cfo_delta_hz=b[CFO] - a[CFO],
                    integer_epoch_delta=b[EPOCH] - a[EPOCH], fractional_epoch_delta=b[OFFSET] - a[OFFSET],
                    changed_fields=[k for k in ROW_FIELDS if a[k] != b[k]], installed=a, mixed=b)],
                    ambiguous_before=[], ambiguous_after=[])
    same = [a for a in before if a in after]
    return dict(lost=[], gained=[], retained=[dict(installed=a, mixed=a, cfo_delta_hz=0.0, integer_epoch_delta=0,
                fractional_epoch_delta=0.0, changed_fields=[]) for a in same],
                ambiguous_before=[a for a in before if a not in same], ambiguous_after=[b for b in after if b not in same])


def certified_original(archived, stock):
    if metadata(archived) != metadata(stock) or len(archived["candidates"]) != len(stock["candidates"]):
        return False
    for a, b in zip(archived["candidates"], stock["candidates"], strict=True):
        for name in ROW_FIELDS:
            if name in SCORES:
                if abs(a[name] - b[name]) > 1e-10:
                    return False
            elif a[name] != b[name]:
                return False
    return True


def overlap(full, stock, mixed, witness, owners):
    views, archive_lanes = prefix_scope(full, stock, mixed, witness)
    archive, original, candidate = (views[n][0] for n in ("archived", "installed_prefix", "mixed_prefix"))
    different = [i for i in range(MEMBER_VISITS) if len({i in excluded for _, excluded in views.values()}) != 1]
    session = full["source"]["session_id"]
    before = set(archive) & set(original)
    disagreements = sorted(lane for lane in before if not certified_original(archive[lane], original[lane]))
    result, replacements, prefix_ids = [], {}, set()
    for key in sorted(set(archive) | set(original) | set(candidate)):
        rows = [view.get(key) for view in (archive, original, candidate)]
        left, middle, right = rows
        identity = observation_id(session, next(row for row in rows if row is not None))
        prefix_ids.add(identity)
        related = {mode: {arm: owners[mode][arm].get(identity) for arm in ARMS} for mode in MODES}
        contrast = None
        if middle is not None and right is not None:
            contrast = factor_contrast(middle["candidates"], right["candidates"])
        if left is not None and right is not None and metadata(left) == metadata(right):
            replacements[key] = left if middle is not None and middle["candidates"] == right["candidates"] else right
        result.append(dict(visit=key[0], receiver=key[1], channel=next(r["channel"] for r in rows if r is not None),
                           original_observation_id=identity, owners=related,
                           archived_factors=left["candidates"] if left else None,
                           installed_factors=middle["candidates"] if middle else None,
                           mixed_factors=right["candidates"] if right else None, contrast=contrast,
                           corroborated=key in before and key not in disagreements))
    checks = dict(admission_differences=different, original_lane_differences=disagreements,
                  incomplete_mixed_metadata=sorted(set(archive) - set(replacements)),
                  exclusion_provenance_equal=len({json.dumps(excluded, sort_keys=True) for _, excluded in views.values()}) == 1)
    can_splice = (not any(checks[k] for k in ("admission_differences", "original_lane_differences", "incomplete_mixed_metadata"))
                  and checks["exclusion_provenance_equal"])
    output = [replacements.get(key, row) for key, row in archive_lanes.items()] if can_splice else None
    totals = {mode: {arm: dict(full=len(owners[mode][arm]), first_64=len(owners[mode][arm].keys() & prefix_ids))
                     for arm in ARMS} for mode in MODES}
    counters = {name: {axis: Counter() for axis in ("total", "by_receiver", "by_channel")}
                for name in ("lost", "gained", "retained", "ambiguous_before", "ambiguous_after")}
    deltas = {"all": []} | {f"{mode}/{arm}": [] for mode in MODES for arm in ARMS}
    for lane in result:
        if lane["contrast"] is None or not lane["corroborated"]:
            continue
        for name, bucket in counters.items():
            count = len(lane["contrast"][name])
            bucket["total"]["native"] += count
            bucket["by_receiver"][lane["receiver"]] += count
            bucket["by_channel"][lane["channel"]] += count
            for mode in MODES:
                for arm in ARMS:
                    owns = lane["owners"][mode][arm] is not None
                    label = f"{mode}/{arm}"
                    if name == "gained":
                        owns = False
                    bucket["total"][label + ("/owned_lane" if owns else "/unassigned_lane")] += count
                    if name == "retained" and owns and len(lane["installed_factors"]) == len(lane["mixed_factors"]) == 1:
                        deltas[label].append(lane["contrast"][name][0]["cfo_delta_hz"])
            if name == "retained" and len(lane["installed_factors"]) == len(lane["mixed_factors"]) == 1:
                deltas["all"].append(lane["contrast"][name][0]["cfo_delta_hz"])
    distribution = {k: (dict(count=len(v), minimum_hz=min(v), median_hz=median(v), maximum_hz=max(v),
                                max_absolute_hz=max(map(abs, v))) if v else dict(count=0)) for k, v in deltas.items()}
    return dict(checks=checks, can_splice=can_splice, changes=sum(a != b for a, b in zip(archive_lanes.values(), output, strict=True))
                if output is not None else None, owner_counts=totals, membership=counters, signed_cfo=distribution, lanes=result), output


def prefix_packets(producer, pin, witness, request):
    """Verify a sealed detector-pair envelope before inspecting its rows."""
    from empty_bootstrap import bind_native
    from leo.contracts.digests import canonical_digest

    sealed = json.loads(checked(producer, pin))
    binding = sealed["original"]
    hashes = [row["iq_sha256"] for row in witness["visits"]]
    if (binding["session"] != request["session"] or binding["inventory"] != request["inventory"]
            or binding["raw_authority"] != request["raw_authority"] or binding["segment"] != witness["segment"]
            or binding["member"] != witness["member"] or sealed["position_runs"] != 0
            or sealed["phase"] != "before_held_selector" or sealed["visit_iq_sha256"] != hashes):
        raise ValueError("The sealed detector pair differs from the original signed first member")
    inventory = sealed["prefix_inventory"]
    inventory_pin = canonical_digest(inventory)
    if inventory["window_count"] != MEMBER_VISITS or inventory["original_inventory_sha256"] != request["inventory"]:
        raise ValueError("The independent prefix must commit its limited coverage and original inventory")
    session = "fast-" + inventory_pin[7:39]
    raw = canonical_digest([inventory_pin, hashes])
    packets = {}
    for mode in ("installed", "mixed"):
        run = sealed["runs"][mode]
        path = Path(run["native_file"])
        if not path.is_relative_to(producer.parent) or path.name != "detections.json" or run["exit_code"] != 0:
            raise ValueError("Expected one completed certified native packet per receiver")
        native = json.loads(checked(path, run["native_sha256"]))
        recipe = run["detector_sha256"]
        if (native["source"]["raw_recording_authority_digest"] != raw
                or (mode == "installed" and recipe != "sha256:2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5")
                or (mode == "mixed" and run["recipe"]["aperture_samples"] != [200_000, 80_000])
                or (mode == "mixed" and recipe != canonical_digest(run["recipe"]))):
            raise ValueError("The original detector or authenticated 20/8 receiver recipe changed")
        bind_native(native, session, inventory_pin, recipe[7:], expected=run["native_sha256"])
        packets[mode] = native
    return packets


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", type=Path, help="staged signed segment, metadata access only")
    parser.add_argument("output", type=Path)
    parser.add_argument("--prefix-receipt", type=Path)
    parser.add_argument("--prefix-receipt-sha256")
    args = parser.parse_args()
    if (args.prefix_receipt is None) != (args.prefix_receipt_sha256 is None):
        parser.error("provide both the sealed detector-pair envelope and its external digest")
    docs, lanes, excluded, owners, trials = archived()
    witness, coverage = archive_prefix(args.stage, docs, lanes, excluded, owners)
    paired = None
    if args.prefix_receipt is not None:
        packets = prefix_packets(args.prefix_receipt, args.prefix_receipt_sha256, witness, docs["request.json"])
        paired, _ = overlap(docs["native.json"], packets["installed"], packets["mixed"], witness, owners)
    write(args.output, dict(scope="archived owner exposure against signed original first member metadata",
                            original_files=PINS, manifest=witness["segment"], member=witness["member"],
                            published=trials, archive_prefix=coverage, prefix_receiver_measured=paired is not None,
                            prefix_receipt_sha256=args.prefix_receipt_sha256, paired_overlap=paired,
                            new_position_runs=0, waveform_reads=0))


if __name__ == "__main__":
    main()
