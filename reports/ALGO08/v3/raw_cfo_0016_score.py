"""Check signed factor support and both publication arms after the raw CFO transfer."""

import argparse
from collections import Counter
import json
from math import sqrt
from pathlib import Path
from statistics import mean, median

from empty_bootstrap import checked
from raw_0016_best_score import ARMS, STOCK_OWNERS, STOCK_OWNERS_SHA, process_rows
from raw_0016_best_trial import CASE, ORIGINAL, seal, sha
from raw_cfo_0016_trial import (
    FAILED, FAILED_CLOCK_SHA, FIRST_CONDITIONING_SHA, HISTORICAL, HISTORICAL_SCORE, HISTORICAL_SEAL, ORDER, PROTOCOL_SHA,
)
from short_cfo_raw import CFO, recipe


def compare_factors(stock, mixed, refined):
    from mixed_aperture_receiver import FULL_RULE
    from reports.ALGO08.v3.mixed_aperture_trial import encoded
    from reports.ALGO08.v3.short_cfo_refine import factor_reference

    def rows(packet):
        return packet["source"]["probes"]

    def opportunity(row):
        return {key: value for key, value in row.items() if key != "candidates"}

    def stream_key(row):
        return row["edge"], row["channel"], row["actual_rf_hz"]

    stock_rows, mixed_rows, refined_rows = map(rows, (stock, mixed, refined))
    stream_visits, lanes = Counter(), {}
    changes, reference, labels = [], [], {}
    for index, (named, before, after) in enumerate(zip(stock_rows, mixed_rows, refined_rows, strict=True)):
        if opportunity(named) != opportunity(before) or opportunity(before) != opportunity(after):
            raise ValueError("Signed opportunity or timing changed across receivers")
        lane = before["receiver_id"]
        stream = stream_key(before)
        if lane != index % 2 or lane and (before["visit_index"] != mixed_rows[index-1]["visit_index"]
                                          or stream != stream_key(mixed_rows[index-1])):
            raise ValueError("Expected the original ordered stereo opportunity sequence")
        index_in_stream = stream_visits[stream]
        mode = FULL_RULE[index_in_stream % len(FULL_RULE)]
        if lane == 1:
            stream_visits[stream] += 1
        label = f"{mixed['source']['session_id']}:{lane}:{before['valid_start_counter']}"
        identifier = "sha256:"+sha(label.encode())
        if identifier in labels:
            raise ValueError("Duplicate physical opportunity")
        labels[identifier] = lane
        counts = lanes.setdefault((mode, lane), Counter())
        old_factors, new_factors, stock_factors = [row["candidates"] for row in (before, after, named)]
        counts.update(dict(opportunities=1, stock=len(stock_factors), unrefined=len(old_factors), refined=len(new_factors),
                           stock_only=int(bool(stock_factors) and not old_factors),
                           mixed_only=int(bool(old_factors) and not stock_factors)))
        if len(old_factors) != len(new_factors):
            raise ValueError("Refinement changed which factors passed the original verifier")
        if mode == "full" and old_factors != new_factors:
            raise ValueError("Refinement changed a full anchor")
        if mode == "full" or not old_factors:
            continue
        (old,), (new,) = old_factors, new_factors
        if {k: v for k, v in old.items() if k != CFO} != {k: v for k, v in new.items() if k != CFO}:
            raise ValueError("Refinement changed a non-CFO factor value")
        if old[CFO] != new[CFO]:
            counts["changed"] += 1
            changes.append(dict(owner_id=identifier, radio=lane, visit=before["visit_index"], channel=before["channel"],
                                signed_before_hz=old[CFO], signed_after_hz=new[CFO], change_hz=new[CFO]-old[CFO]))
        donor, match = factor_reference(encoded(named), encoded(before)[0])
        if match and match["matched"]:
            reference.append(dict(radio=lane, visit=before["visit_index"], before_hz=old[CFO]-donor[3], after_hz=new[CFO]-donor[3]))
    return dict(lanes=[dict(mode=mode, radio=lane, **counts) for (mode, lane), counts in sorted(lanes.items())],
                changes=changes, reference=reference), labels


def matched_rms(rows):
    if not rows:
        return dict(matched=0)
    return dict(matched=len(rows), improved=sum(abs(row["after_hz"]) < abs(row["before_hz"]) for row in rows),
                worsened=sum(abs(row["after_hz"]) > abs(row["before_hz"]) for row in rows),
                rms_hz={name: sqrt(mean(row[f"{name}_hz"]**2 for row in rows)) for name in ("before", "after")},
                median_absolute_hz={name: median(abs(row[f"{name}_hz"]) for row in rows) for name in ("before", "after")})


def owner_comparisons(runs, labels, changed):
    from leo.contracts.digests import canonical_digest
    from prospective_0316_solver import owner_delta

    if runs["refined"]["science"]["receipt"]["decision"] != "complete":
        return None
    archived = json.loads(checked(STOCK_OWNERS, STOCK_OWNERS_SHA))
    if archived["receipt"]["terminal_sha256"] != runs["named"]["science"]["receipt"]["terminal_sha256"]:
        raise ValueError("Ordered named owners belong to a different raw publication")
    rows = {"named": archived["selected_rows"]} | {key: runs[key]["research"]["selected_rows"] for key in ("mixed", "refined")}
    for name, arms in rows.items():
        for arm, selected in arms.items():
            if not all(oid in labels for oid, _, _ in selected) or canonical_digest({oid: sat for oid, sat, _ in selected}) != runs[name]["science"]["owners"][arm]:
                raise ValueError("Selected association rows do not reproduce published owner authority")
    results = {}
    for name in ("named", "mixed"):
        arms = {}
        for arm in ARMS:
            previous, current = rows[name][arm], rows["refined"][arm]
            lookup = {row[0]: row[1:] for row in previous}
            scope = dict(
                all=owner_delta(previous, current),
                predictive=owner_delta([row for row in previous if row[2] == "predictive"], [row for row in current if row[2] == "predictive"]),
                owned_updated_cfo=sum(row[0] in changed for row in current),
            )
            scope["per_radio"] = {str(radio): dict(before=sum(labels[oid] == radio for oid, _, _ in previous),
                after=sum(labels[oid] == radio for oid, _, _ in current),
                shared_owner_changed=sum(labels[oid] == radio and lookup[oid] != [sat, role] for oid, sat, role in current if oid in lookup))
                for radio in (0, 1)}
            arms[arm] = scope
        results[name] = arms
    return results


def score(root, output):
    from aperture_trial import read, write
    from full_short_run import RECIPE_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from local_future_cli_trial import native_packet
    from triage_bounds import calibration_comparison

    witness = root/"prediction-seal.json"
    expected = seal(root, ORDER) | {"preflight.json": sha((root/"preflight.json").read_bytes())}
    if read(witness) != expected or json.loads(checked(HISTORICAL/"prediction-seal.json", HISTORICAL_SEAL)) != seal(HISTORICAL):
        raise ValueError("A previously sealed raw publication changed before scoring")
    admission = read(root/"admission.json")
    historical = json.loads(checked(HISTORICAL/"result.json", HISTORICAL_SCORE))
    prior = historical["admission"]
    if (admission["selection"]["protocol_sha256"] != PROTOCOL_SHA or tuple(admission["order"]) != ORDER
            or any(admission[key] != prior[key] for key in ("case", "inventory", "recording", "manifests", "raw_authority", "session", "offer_sha256",
                                                           "archive", "cutoff_utc_ns", "route_flags", "sources", "stock", "library_sha256"))):
        raise ValueError("The fresh receiver changed the original workload or common solver build")
    proposed_recipe = recipe(checked_recipe(), RECIPE_SHA)
    refinement_identifier = canonical_digest(proposed_recipe)
    current, = process_rows(root, admission, modes=ORDER, candidate_recipe=refinement_identifier.removeprefix("sha256:")).values()
    if current["bootstrap"]["receiver_recipe"] != proposed_recipe or current["bootstrap"]["detector_recipe_sha256"] != refinement_identifier:
        raise ValueError("The refined native packet lacks its own authenticated detector identity")
    runs = {"named": historical["original"]["stock"], "mixed": historical["original"]["candidate"], "refined": current}
    if len({run["opportunities"] for run in runs.values()}) != 1:
        raise ValueError("The physical receiver opportunities changed")
    packets = [read(native_packet(base/mode)) for base, mode in ((HISTORICAL, "stock"), (HISTORICAL, "candidate"), (root, "candidate"))]
    factors, labels = compare_factors(*packets)
    audit = current["bootstrap"]["receiver_audit"]["native"]["cfo_refinement"]
    if (sum(row["counts"]["changed"] for row in audit["lanes"]) != len(factors["changes"])
            or sum(row["counts"]["attempted"] for row in audit["lanes"])
            != sum(row["unrefined"] for row in factors["lanes"] if row["mode"] == "short_primary")):
        raise ValueError("Authenticated raw receiver audit differs from the actual factor rows")
    references = factors["reference"]
    factors["rms"] = dict(all=matched_rms(references), **{str(radio): matched_rms([row for row in references if row["radio"] == radio]) for radio in (0, 1)})
    owners = owner_comparisons(runs, labels, {row["owner_id"] for row in factors["changes"]})
    geographic = calibration_comparison({name: run["science"] for name, run in runs.items()}, CASE.id)
    write(output, dict(pre_score_sha256=sha(witness.read_bytes()), admission=admission, runs=runs, factors=factors, owners=owners,
                       geographic=geographic, conditioning=read(root/"conditioning.json"),
                       first_conditioning=json.loads(checked(FAILED/"conditioning.json", FIRST_CONDITIONING_SHA)),
                       failed_startup=json.loads(checked(FAILED/"candidate-clock.json", FAILED_CLOCK_SHA))["clock"],
                       preflight=read(root/"preflight.json")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    score(args.root, args.output)
