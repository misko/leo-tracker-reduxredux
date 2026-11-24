"""Decompose signed paired DS30 errors without exporting position coordinates."""

import argparse
from collections import Counter
import json
from math import hypot, isclose
from pathlib import Path

from tools.pipeline_eval.scoring import distance_km

from .ds30_oracle_routing import CAMPAIGN, OVERLAY, PLAN, RELOCATION, checked, digest, frozen_order
from .ds30_position_moments import TOLERANCE, decompose, east_north_km
from .full_successor_score import ARMS, BUILDS, PINS, REFERENCE, VERIFIED, paired_rows, roster


INITIAL = tuple(f"DS30-{label}" for label in (
    "0107", "0049", "0178", "0019", "0274", "0330", "0397", "0452",
    "0124", "0086", "0220", "0144", "0170", "0262", "0102", "0087"))
PROSPECTIVE = ("DS30-0105", "DS30-0244", "DS30-0183")
EXPORT = "sha256:8891b5098c48e78d23c7e62d9c56a2a5d7ca24dc35ab5d3a1626e53b143cf0c2"
EXPORT_SEAL = "sha256:d3e2fea8c9d1761e525bb4a9844e5261f7b267f6afb7df79bd8623743f0a2dda"
INITIAL_RESULT = "sha256:71ea4041f90fba34af3745582c6d217c5ae3fa1a1cbdfe545ca97cbcdade1e09"


def analyze(captures):
    outcomes = {role: dict(Counter(rows[role]["outcome"] for _, _, rows in captures)) for role in BUILDS}
    results = {}
    for arm in ARMS:
        offsets = {role: [] for role in BUILDS}
        fixes, scored = (Counter(dict.fromkeys(BUILDS, 0)) for _ in range(2))
        shared = []
        max_distance_residual_km = 0.
        for case, reference, rows in captures:
            errors = {role: distance_km(reference, rows[role]["arms"][arm]["latlon"]) for role in BUILDS}
            for role, error in errors.items():
                fixes[role] += int(rows[role]["arms"][arm]["latlon"] is not None)
                scored[role] += int(error is not None)
            if None in errors.values():
                continue
            shared.append(case)
            for role, error in errors.items():
                value = east_north_km(reference, rows[role]["arms"][arm]["latlon"])
                distance = hypot(*value)
                if not isclose(distance, error, abs_tol=TOLERANCE, rel_tol=TOLERANCE):
                    raise ValueError("East/north radial error must reproduce the official scoring distance")
                max_distance_residual_km = max(max_distance_residual_km, abs(distance-error))
                offsets[role].append(value)
        if not shared:
            results[arm] = dict(shared=[], fixes=dict(fixes), scored=dict(scored),
                                builds={role: {"n": 0} for role in BUILDS}, successor_minus_installed=None,
                                max_distance_residual_km=None)
            continue
        roles = {role: decompose(vertices) for role, vertices in offsets.items()}
        original, successor = (roles[role] for role in BUILDS)
        excess = {key: successor[key]-original[key] for key in original if key.endswith(("_km2", "_km"))
                  and key != "max_identity_residual_km2"}
        if not isclose(excess["radial_mse_km2"], excess["squared_mean_offset_km2"]+excess["centered_mse_km2"],
                       abs_tol=TOLERANCE, rel_tol=TOLERANCE):
            raise ValueError("The build differences must preserve the decomposition")
        results[arm] = dict(shared=shared, fixes=dict(fixes), scored=dict(scored), builds=roles, successor_minus_installed=excess,
                            max_distance_residual_km=max_distance_residual_km)
    return dict(assigned=len(captures), outcomes=outcomes, arms=results)


def verified_capture(campaign, entry, rows, assigned, overlay):
    case = entry["case"]
    folder = campaign/("relocation" if case == RELOCATION else "cases")/case
    body = (folder/"pair.json").read_bytes()
    pair = json.loads(body)
    if (pair["state"] != "observed_pair" or not pair["verified_pair"] or not pair["chronological"]
            or pair["actual_order"] != entry["order"] or set(rows) != set(BUILDS)
            or (case == RELOCATION and pair != overlay["paired_scope"])):
        raise ValueError(f"The original pair is incomplete or does not match the order for {case}")
    for role, row in rows.items():
        for key in ("assigned_rank", "case_id", "raw_identity_sha256", "manifest_raw_authority_sha256"):
            if row[key] != entry[key]:
                raise ValueError(f"Frozen recording identity changed for {case}")
        relative = row["attempt"]
        location = campaign/relative
        pin = pair["attempt_result_sha256"][role]
        if not location.is_relative_to(folder/role):
            raise ValueError(f"The attempt path escapes the assigned case and algorithm for {case}/{role}")
        parts = location.relative_to(folder/role).parts
        if (len(parts) != 2 or not parts[0].startswith("attempt-") or not parts[0][8:].isdigit()
                or parts[1] not in {"result.json", "revalidation.json"}):
            raise ValueError(f"The selected original attempt path has an unexpected shape for {case}/{role}")
        if (not row["verified_pair"] or not row["acquisition_verified"] or row["outcome"] not in VERIFIED
                or row["actual_order"] != entry["order"] or row["first"] != entry["order"][0]
                or row["generation"] != pair["generation"] or row["authority_sha256"] != pair["authority_sha256"]
                or pin != row["attempt_result_sha256"] or location.resolve(strict=True) != location
                or (case == RELOCATION and overlay["paired_attempts"][role] != dict(path=relative, sha256=pin))):
            raise ValueError(f"The selected signed worker changed for {case}/{role}")
        attempt = json.loads(checked(location, pin))
        evidence = attempt["evidence"]
        exported = {name: dict(latlon=None, rf_rms_hz=None) | evidence["arms"][name] for name in ARMS}
        if (attempt["algorithm"] != role or attempt["outcome"] != row["outcome"] or exported != row["arms"]
                or attempt["generation"] != pair["generation"] or attempt["authority_sha256"] != pair["authority_sha256"]
                or evidence["raw_authority"] != row["raw_authority_sha256"]
                or evidence["receipt"].get("terminal_sha256") != row["terminal_sha256"]):
            raise ValueError(f"Export differs from the signed original terminal for {case}/{role}")
    paired_rows(rows.values(), {case: assigned})
    return (case, assigned["reference"], rows), dict(pair_sha256=digest(body), attempts=pair["attempt_result_sha256"])


def campaign_order(campaign):
    plan = json.loads(checked(campaign/"plan.json", PLAN))
    ordered = frozen_order(plan)
    selection = INITIAL+PROSPECTIVE
    if tuple(entry["case"] for entry in ordered[:len(selection)]) != selection:
        raise ValueError("The two frozen cohorts must match the plan's original execution order")
    return ordered


def selected_rows(body, selection):
    rows = {case: {} for case in selection}
    for line in body.splitlines():
        row = json.loads(line)
        if row["case"] in rows:
            group = rows[row["case"]]
            if row["algorithm"] not in BUILDS or row["algorithm"] in group:
                raise ValueError("The snapshot has ambiguous selected arms")
            group[row["algorithm"]] = row
    return rows


def verified_overlay(campaign, seal):
    overlay_root = campaign/"relocation"/RELOCATION
    overlay = json.loads(checked(overlay_root/"overlay.json", OVERLAY))
    if (overlay["case"] != RELOCATION or overlay["plan_sha256"] != PLAN or overlay["proof_path"] != f"relocation/{RELOCATION}/proof.json"
            or overlay["proof_sha256"] != seal["proofs"][RELOCATION]):
        raise ValueError("The adopted relocation does not bind the frozen original")
    checked(overlay_root/"proof.json", overlay["proof_sha256"])
    checked(overlay_root/"native-encoded-auth.json", overlay["encoded_auth_sha256"])
    return overlay


def study(campaign, snapshot):
    ordered = campaign_order(campaign)
    seal = json.loads(checked(snapshot/"rows-with-relocations-seal.json", EXPORT_SEAL))
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT:
        raise ValueError("The planned snapshot export binding changed")
    rows = selected_rows(checked(snapshot/"rows-with-relocations.jsonl", EXPORT), INITIAL+PROSPECTIVE)
    overlay = verified_overlay(campaign, seal)
    assigned = roster()
    selected = [verified_capture(campaign, entry, rows[entry["case"]], assigned[entry["case"]], overlay)
                for entry in ordered[:len(INITIAL)]]
    pending = {case: {role: rows[case][role]["admission_state"] for role in BUILDS} for case in PROSPECTIVE}
    if any(row["verified_pair"] for case in PROSPECTIVE for row in rows[case].values()):
        raise ValueError("The frozen pending states require a separate prospective receipt")
    return dict(initial=analyze([capture for capture, _ in selected]), prospective=dict(assigned=list(PROSPECTIVE), pending=pending),
                original_scope=dict(plan=PLAN, combined_export=EXPORT, export_seal=EXPORT_SEAL, references=REFERENCE,
                                    relocation=OVERLAY, builds=PINS, verified_pairs={capture[0]: proof for capture, proof in selected}))


def pending_pairs(campaign, entries):
    pending = {}
    for entry in entries:
        case = entry["case"]
        path = campaign/"cases"/case/"pair.json"
        if not path.is_file():
            pending[case] = "no_pair_receipt"
            continue
        pair = json.loads(path.read_bytes())
        if pair["state"] != "observed_pair" or not pair["verified_pair"] or not pair["chronological"]:
            pending[case] = pair["state"]
        elif pair["actual_order"] != entry["order"]:
            raise ValueError(f"The sealed original pair changed the frozen order for {case}")
    return pending


def prospective(campaign, snapshot=None):
    ordered = campaign_order(campaign)
    entries = ordered[len(INITIAL):len(INITIAL)+len(PROSPECTIVE)]
    pending = pending_pairs(campaign, entries)
    metadata = dict(assigned=list(PROSPECTIVE), plan=PLAN, initial_result=INITIAL_RESULT, references=REFERENCE, builds=PINS)
    if pending:
        return dict(ready=False, **metadata, pending=pending)
    snapshot = campaign if snapshot is None else snapshot
    body = (snapshot/"rows.jsonl").read_bytes()
    rows = selected_rows(body, PROSPECTIVE)
    pending = {case: "unverified_in_current_export" for case, group in rows.items()
               if set(group) != set(BUILDS) or not all(row["verified_pair"] for row in group.values())}
    if pending:
        return dict(ready=False, **metadata, pending=pending)
    seal_body = (snapshot/"rows-with-relocations-seal.json").read_bytes()
    seal = json.loads(seal_body)
    if seal["plan_sha256"] != PLAN:
        raise ValueError("The live overlay export belongs to a different campaign")
    ordinary_digest = digest(body)
    if seal["ledger_snapshot_sha256"] != ordinary_digest:
        return dict(ready=False, **metadata, pending={"combined_export": "ordinary_snapshot_not_yet_sealed"})
    combined = checked(snapshot/"rows-with-relocations.jsonl", seal["combined_sha256"])
    rows_with_relocation = selected_rows(combined, PROSPECTIVE+(RELOCATION,))
    if any(rows_with_relocation[case] != rows[case] for case in PROSPECTIVE):
        raise ValueError("The combined seal must cover all six unchanged prospective worker rows")
    overlay = verified_overlay(campaign, seal)
    relocation_row = rows_with_relocation[RELOCATION]
    relocation_entry = next(entry for entry in ordered if entry["case"] == RELOCATION)
    assigned = roster()
    _, checked_relocation = verified_capture(campaign, relocation_entry, relocation_row, assigned[RELOCATION], overlay)
    selected = [verified_capture(campaign, entry, rows[entry["case"]], assigned[entry["case"]], overlay) for entry in entries]
    result = analyze([capture for capture, _ in selected])
    meaningful = {arm: len(group["shared"]) >= 2 for arm, group in result["arms"].items()}
    return dict(ready=True, **metadata, ordinary_export=ordinary_digest, relocation=OVERLAY,
                combined_export=seal["combined_sha256"], combined_seal=digest(seal_body),
                ordinary_combined_rows_equal=True, relocation_pair=checked_relocation,
                verified_pairs={capture[0]: proof for capture, proof in selected}, result=result, spread_comparison_available=meaningful)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--prospective", action="store_true")
    args = parser.parse_args()
    output = prospective(args.campaign, args.snapshot) if args.prospective else study(args.campaign, args.snapshot or args.campaign)
    print(json.dumps(output, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
