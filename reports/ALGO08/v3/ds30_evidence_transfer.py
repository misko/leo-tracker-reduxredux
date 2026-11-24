"""Compare sealed 20/8 and 20 ms evidence without opening original sample or orbit data."""

import argparse
import json
from math import remainder, sqrt
import os
from pathlib import Path
from statistics import fmean, median
import sys

from tools.pipeline_eval.scoring import distance_km

from .ds30_oracle_routing import CAMPAIGN, OVERLAY, PLAN, checked, frozen_order
from .full_successor_score import ARMS, BUILDS, roster


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # Shared research detector helpers use local imports.
import signed_cfo_time_readout as signed
from matched_donor_0049 import FAC_PERIOD, MAX_CFO_HZ, MAX_EPOCH_SAMPLES
from signed_cfo_time import epoch


SEEN = {
    "DS30-0049": (2, "7514497ea681194487e8d85aecf2d739e996abf2b90566d446f81fe38875c36b"),
    "DS30-0452": (2, "ce1d7f639427ea320ddcb877117338cbaeb19b66589cf36551a2a0c3c0ef8e40"),
    "DS30-0124": (1, "a92a58d7e805380cd4966f6abfd98fb5242204095273f8fe06c755514e81ed3d"),
    "DS30-0170": (1, "dacfb564e47a869a9f15ebc49057d1fee062cb81f2f90da78476ff4dc22103f6"),
}
PROSPECTIVE = ("DS30-0105", "DS30-0244", "DS30-0183")
INSTALLED_0049 = Path("/tmp/leo-v3-0049-saved-cross-proof02/installed-installed/crossover-worker.json")
INSTALLED_0049_SHA = "86d3b27db6e1bb85f69e180228ff6b7b977d4779f1b42c018ce054475c2c3141"
CLASSES = ("both_empty", "candidate_empty", "sparse_only", "signed_shift", "epoch_only", "same_carrier")


def deny_backing(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.fsdecode(args[0])).resolve()
        if (path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01")
                or "tle" in path.parts or path.name.endswith((".ci16.zst", ".tle", ".tle.gz"))):
            raise ValueError("This study accepts saved detector packets and signed receipts only")


def classify(before, after):
    if before is None or after is None:
        return ("sparse_only" if after else "candidate_empty" if before else "both_empty"), None
    delta_hz = after["fractional_tracking_cfo_hz"]-before["fractional_tracking_cfo_hz"]
    delta_samples = remainder(epoch(after)-epoch(before), FAC_PERIOD)
    if abs(delta_hz) > MAX_CFO_HZ:
        return "signed_shift", None
    if abs(delta_samples) > MAX_EPOCH_SAMPLES:
        return "epoch_only", None
    return "same_carrier", (delta_hz, delta_samples)


def layer(members, rosters, *, arm=None):
    counts = dict.fromkeys(CLASSES, 0)
    errors = []
    owners = {role: None if role not in rosters else dict.fromkeys(CLASSES, 0) for role in BUILDS}
    jointly_owned = None if len(rosters) != len(BUILDS) else dict(shared_ids=0, shared_satellite=0, shared_satellite_role=0,
                                                                 shared_by_state=dict.fromkeys(CLASSES, 0))
    for oid, status, delta in members:
        counts[status] += 1
        if delta is not None:
            errors.append(delta)
        if arm is None:
            continue
        selected = {role: maps[arm].get(oid) for role, maps in rosters.items()}
        for role, owner in selected.items():
            if owner is not None:
                owners[role][status] += 1
        if jointly_owned is not None and all(selected.values()):
            old, new = (selected[role] for role in BUILDS)
            jointly_owned["shared_ids"] += 1
            jointly_owned["shared_satellite"] += int(old[0] == new[0])
            jointly_owned["shared_satellite_role"] += int(old == new)
            jointly_owned["shared_by_state"][status] += 1
    if arm is not None:
        if ((owners["installed"] and (owners["installed"]["both_empty"] or owners["installed"]["sparse_only"]))
                or (owners["successor"] and (owners["successor"]["both_empty"] or owners["successor"]["candidate_empty"]))):
            raise ValueError("A signed owner has no admitted passed factor in its calibrated build")
        return dict(owners={r: None if a is None else dict(total=sum(a.values()), states=a) for r,a in owners.items()},
                    jointly_owned=jointly_owned)
    stock_positive = sum(counts[s] for s in ("candidate_empty", "signed_shift", "epoch_only", "same_carrier"))
    candidate_positive = sum(counts[s] for s in ("sparse_only", "signed_shift", "epoch_only", "same_carrier"))
    return dict(lanes=len(members), states=counts, installed_positive=stock_positive, candidate_positive=candidate_positive,
                both_positive=counts["signed_shift"]+counts["epoch_only"]+counts["same_carrier"],
                same_carrier_hz_rms=sqrt(fmean(x*x for x,_ in errors)) if errors else None,
                same_carrier_hz_median=median(x for x,_ in errors) if errors else None,
                same_carrier_epoch_rms=sqrt(fmean(x*x for _,x in errors)) if errors else None)


def measure(stock, candidate, rosters):
    left, right = map(signed.opportunities, (stock, candidate))
    signed.bind_pair(stock, candidate, left, right)
    for arms in rosters.values():
        if set(arms) != set(ARMS) or any(not values.keys() <= right.keys() for values in arms.values()):
            raise ValueError("Signed owner rows are outside the two calibrated native opportunity views")
    lanes = {period: {radio: [] for radio in (0, 1)} for period in ("short", "anchor")}
    for oid, row in right.items():
        period = "short" if row["short"] else "anchor"
        status, delta = classify(left[oid]["factor"], row["factor"])
        lanes[period][row["radio"]].append((oid, status, delta))
    return {period: {radio: dict(**layer(members, rosters),
                arms={arm: layer(members, rosters, arm=arm) for arm in ARMS})
               for radio,members in [("rx0", by_radio[0]), ("rx1", by_radio[1]), ("both", by_radio[0]+by_radio[1])]}
            for period,by_radio in lanes.items()}


def case_folder(campaign, case):
    return campaign/("relocation" if case == "DS30-0452" else "cases")/case


def attempts(folder, pair):
    return {role: folder/role/f"attempt-{pair['generation']:06d}" for role in BUILDS}


def choose_prospective(campaign):
    snapshot = {}
    for case in PROSPECTIVE:
        folder = case_folder(campaign, case)
        if not (folder/"pair.json").is_file():
            snapshot[case] = dict(pair=False, attempt_results={role: bool(list((folder/role).glob("attempt-*/result.json")))
                                                              for role in BUILDS})
            continue
        pair = signed.document(folder/"pair.json")
        verified = pair.get("state") == "observed_pair" and pair.get("verified_pair") is True
        present = {role: dict(result=(root/"result.json").is_file(),
                             native=len(list((root/"publication/fast-scan-automatic-work").glob("*/detections.json"))) == 1)
                   for role,root in attempts(folder, pair).items()} if verified else {}
        snapshot[case] = dict(pair=True, verified=verified, attempts=present)
        if verified and all(r["result"] and r["native"] for r in present.values()):
            return case, snapshot
    return None, snapshot


def bind_publication(folder, pin, expected_role, pair):
    attempt = signed.document(folder/"result.json", pin)
    science = attempt["evidence"]
    provenance = attempt["raw_identity"]
    receipt = science["receipt"]
    pub = folder/"publication"
    terminal = signed.document(pub/"fast-scan-automatic-work"/receipt["run_id"]/"terminal.json", receipt["terminal_sha256"])
    expected_decision = {"complete": "ok", "withheld": "withheld"}
    if (attempt["algorithm"] != expected_role or attempt["generation"] != pair["generation"]
            or attempt["authority_sha256"] != pair["authority_sha256"] or attempt["process"]["exit_code"]
            or attempt["outcome"] not in expected_decision or terminal["decision"] != expected_decision[attempt["outcome"]]
            or terminal["native_sha256"] != attempt["native_sha256"] or terminal["arms"] != science["arms"]
            or terminal["region"] != receipt["region"] or terminal["session_id"] != provenance["session_id"]
            or provenance["raw_authority_sha256"] != science["raw_authority"]):
        raise ValueError("Observed attempt differs from its signed original terminal")
    manifest = None
    if attempt["outcome"] == "complete":
        manifest = signed.document(pub/"fast-scan-standard-v2"/receipt["run_id"]/"final-error-v7/manifest.json")
        if (manifest["input_sha256"] != attempt["native_sha256"] or manifest["terminal_sha256"] != receipt["terminal_sha256"]
                or {a:v["owner_sha256"] for a,v in manifest["arms"].items()} != science["owners"]):
            raise ValueError("Public owner denominators are not bound to the signed terminal")
    return attempt, pub, manifest


def read_case(campaign, case, enrollment):
    folder = case_folder(campaign, case)
    generation, pair_pin = SEEN.get(case, (None, None))
    body = (folder/"pair.json").read_bytes()
    pair = signed.document(folder/"pair.json", pair_pin)
    if (pair["state"] != "observed_pair" or not pair["verified_pair"] or not pair["chronological"]
            or pair["actual_order"] != enrollment["order"] or generation is not None and generation != pair["generation"]):
        raise ValueError("Receiver evidence must be from the original verified paired recording")
    pins = pair["attempt_result_sha256"]
    originals = attempts(folder, pair)
    if case == "DS30-0452":
        overlay = signed.document(folder/"overlay.json", OVERLAY)
        if overlay["paired_scope"] != pair or overlay["plan_sha256"] != PLAN or overlay["case"] != case:
            raise ValueError("Relocated input was not verified against the original admission")
        checked(folder/"proof.json", overlay["proof_sha256"])
        checked(folder/"native-encoded-auth.json", overlay["encoded_auth_sha256"])
        for role in BUILDS:
            entry = overlay["paired_attempts"][role]
            path = campaign/entry["path"]
            if (path != folder/role/"attempt-000001"/"result.json" or entry["sha256"] != pins[role]):
                raise ValueError("Relocation overlay binds different attempts")
            originals[role] = path.parent
    installed, pub_i, manifest_i = bind_publication(originals["installed"], pins["installed"], "installed", pair)
    candidate, pub_c, manifest_c = bind_publication(originals["successor"], pins["successor"], "successor", pair)
    identity = installed["raw_identity"]
    if identity != candidate["raw_identity"]:
        raise ValueError("Comparison must share exact recording, cutoff, inventory and original offer")
    stock = signed.read_native(pub_i, installed["native_sha256"])
    raw = signed.document(pub_c/"unified-short-bootstrap.json")
    sparse, witness, _ = signed.qualified_candidate(pub_c, raw, candidate["native_sha256"], identity["region_sha256"])
    if (stock["provenance"]["detector_sha256"] != "sha256:"+signed.FULL
            or stock["source"]["raw_recording_authority_digest"] != identity["raw_authority_sha256"]
            or stock["source"]["input_manifest_sha256"] != identity["inventory_sha256"]
            or stock["clock_anchor"]["before"]["realtime_ns"] != identity["causal_cutoff_utc_ns"]
            or stock["source"]["session_id"] != identity["session_id"]):
        raise ValueError("Installed full-window provenance differs from the verified request")

    rosters, owner_pins = {}, {}
    notes = {role: "public exact arm totals only" for role in BUILDS}
    if candidate["outcome"] == "complete":
        rosters["successor"] = signed.owners(witness["evidence"]["owner_rows"], candidate["evidence"]["owners"])
        owner_pins["successor"] = signed.tag((pub_c/"exact-named-raw-witness.json").read_bytes())
        notes["successor"] = "frozen successor witness matches both published owner digests"
    if case == "DS30-0049" and INSTALLED_0049.is_file():
        exact = signed.document(INSTALLED_0049, INSTALLED_0049_SHA)
        if (exact["submitted_native_sha256"] != installed["native_sha256"]
                or exact["receipt"]["terminal_sha256"] != installed["evidence"]["receipt"]["terminal_sha256"]):
            raise ValueError("Installed 0049 owner rows bind a different native or terminal")
        rosters["installed"] = signed.owners(exact["ordered_owners"], installed["evidence"]["owners"])
        owner_pins["installed"] = "sha256:"+INSTALLED_0049_SHA
        notes["installed"] = "archived exact saved diagonal matches both published owner digests"
    counts = {role: None if manifest is None else {arm: data["associated_points"] for arm,data in manifest["arms"].items()}
              for role, manifest in zip(BUILDS, (manifest_i,manifest_c), strict=True)}
    if any(counts[role] != {arm: len(rows) for arm,rows in arms.items()} for role,arms in rosters.items()):
        raise ValueError("Per-observation owner maps must reproduce the public totals")
    data = measure(stock, sparse, rosters)
    return dict(casescope="mechanism" if generation is not None else "prospective", generation=pair["generation"],
                custody=dict(pair=signed.tag(body), attempts=pins, folders={role: str(path.relative_to(campaign))
                    for role,path in originals.items()}, native={r: a["native_sha256"] for r,a in zip(
                    BUILDS, (installed, candidate), strict=True)}, owner_sources=owner_pins, raw=identity["raw_authority_sha256"]),
                issued_visits=identity["window_count"], lanes=data, published_owners=counts, owner_coverage=notes)


def outcome(reference, pair):
    results = {}
    for arm in ARMS:
        before, after = (distance_km(reference, attempt["evidence"]["arms"][arm]["latlon"]) for attempt in pair)
        results[arm] = dict(installed_km=before, candidate_km=after,
                            delta_km=None if None in (before,after) else after-before,
                            excess_km2=None if None in (before,after) else after*after-before*before)
    return results


def ranks(report, scores):
    values = {}
    for case in SEEN:
        data = report[case]["lanes"]["short"]["both"]
        counts = data["states"]
        marker = dict(lost_or_shifted=(counts["candidate_empty"]+counts["signed_shift"])/data["installed_positive"],
                      matched_cfo_rms_hz=data["same_carrier_hz_rms"])
        for arm in ARMS:
            roster = data["arms"][arm]["owners"]["successor"]
            marker["sparse_only_claim_fraction_"+arm] = roster["states"]["sparse_only"]/roster["total"]
        values[case] = marker
    ranked = {metric: sorted(SEEN, key=lambda c: -values[c][metric]) for metric in next(iter(values.values()))}
    errors = {arm:sorted(SEEN, key=lambda c: -scores[c][arm]["excess_km2"]) for arm in ARMS}
    return dict(marker_values=values, descending_markers=ranked, descending_excess_squared_error=errors)


def write(output, value):
    with output.open("x") as stream:
        json.dump(value, stream, sort_keys=True, allow_nan=False, separators=(",", ":"))
        stream.write("\n")


def freeze(output, campaign=CAMPAIGN):
    plan = json.loads(checked(campaign/"plan.json", PLAN))
    ordered = {row["case"]: (i,row) for i,row in enumerate(frozen_order(plan))}
    if tuple(sorted(PROSPECTIVE, key=lambda k: ordered[k][0])) != PROSPECTIVE:
        raise ValueError("Prospective order must match the frozen original execution order")
    prospective, status = choose_prospective(campaign)
    cases = {case: read_case(campaign, case, ordered[case][1]) for case in SEEN}
    prospective_note = dict(chosen=prospective, availability=status)
    if prospective is not None:
        try:
            cases[prospective] = read_case(campaign, prospective, ordered[prospective][1])
        except (ValueError, FileNotFoundError) as error:
            prospective_note["unscorable"] = str(error)
    packet_seal = dict(cases=cases, prospective=prospective_note)
    write(output, packet_seal)
    print(signed.tag(output.read_bytes()))


def score(output, frozen, pin, campaign=CAMPAIGN):
    packet_seal = signed.document(frozen, pin)
    cases = packet_seal["cases"]
    enrolled = roster()
    scores = {}
    for case, report in cases.items():
        pins = report["custody"]["attempts"]
        folders = report["custody"]["folders"]
        pubs = [signed.document(campaign/folders[role]/"result.json", pins[role]) for role in BUILDS]
        scores[case] = outcome(enrolled[case]["reference"], pubs)
    write(output, dict(packet_metrics_sha256=pin, scores=scores, rankings=ranks(cases, scores),
                       raw_reads=0, tle_reads=0, solves=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "score"))
    parser.add_argument("output", type=Path)
    parser.add_argument("--frozen", type=Path)
    parser.add_argument("--pin")
    args = parser.parse_args()
    sys.addaudithook(deny_backing)
    if args.action == "freeze":
        freeze(args.output)
    elif args.frozen and args.pin:
        score(args.output, args.frozen, args.pin)
    else:
        parser.error("Independent scoring requires the frozen packet metric file and SHA-256")
