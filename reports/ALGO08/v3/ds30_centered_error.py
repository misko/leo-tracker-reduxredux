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
        if (not row["verified_pair"] or not row["acquisition_verified"] or row["outcome"] not in VERIFIED
                or row["actual_order"] != entry["order"] or row["first"] != entry["order"][0]
                or row["generation"] != pair["generation"] or row["authority_sha256"] != pair["authority_sha256"]
                or pin != row["attempt_result_sha256"] or location.resolve(strict=True) != location
                or not location.is_relative_to(folder/role)
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


def study(campaign, snapshot):
    plan = json.loads(checked(campaign/"plan.json", PLAN))
    ordered = frozen_order(plan)
    selection = INITIAL+PROSPECTIVE
    if tuple(entry["case"] for entry in ordered[:len(selection)]) != selection:
        raise ValueError("The two frozen cohorts must match the plan's original execution order")
    seal = json.loads(checked(snapshot/"rows-with-relocations-seal.json", EXPORT_SEAL))
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT:
        raise ValueError("The planned snapshot export binding changed")
    rows = {case: {} for case in selection}
    for line in checked(snapshot/"rows-with-relocations.jsonl", EXPORT).splitlines():
        row = json.loads(line)
        if row["case"] in rows:
            group = rows[row["case"]]
            if row["algorithm"] not in BUILDS or row["algorithm"] in group:
                raise ValueError("The snapshot has ambiguous selected arms")
            group[row["algorithm"]] = row
    overlay_root = campaign/"relocation"/RELOCATION
    overlay = json.loads(checked(overlay_root/"overlay.json", OVERLAY))
    if (overlay["case"] != RELOCATION or overlay["plan_sha256"] != PLAN or overlay["proof_path"] != f"relocation/{RELOCATION}/proof.json"
            or overlay["proof_sha256"] != seal["proofs"][RELOCATION]):
        raise ValueError("The adopted relocation does not bind the frozen original")
    checked(overlay_root/"proof.json", overlay["proof_sha256"])
    checked(overlay_root/"native-encoded-auth.json", overlay["encoded_auth_sha256"])
    assigned = roster()
    selected = [verified_capture(campaign, entry, rows[entry["case"]], assigned[entry["case"]], overlay)
                for entry in ordered[:len(INITIAL)]]
    pending = {case: {role: rows[case][role]["admission_state"] for role in BUILDS} for case in PROSPECTIVE}
    if any(row["verified_pair"] for case in PROSPECTIVE for row in rows[case].values()):
        raise ValueError("The frozen pending states require a separate prospective receipt")
    return dict(initial=analyze([capture for capture, _ in selected]), prospective=dict(assigned=list(PROSPECTIVE), pending=pending),
                original_scope=dict(plan=PLAN, combined_export=EXPORT, export_seal=EXPORT_SEAL, references=REFERENCE,
                                    relocation=OVERLAY, builds=PINS, verified_pairs={capture[0]: proof for capture, proof in selected}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    parser.add_argument("--snapshot", type=Path)
    args = parser.parse_args()
    print(json.dumps(study(args.campaign, args.snapshot or args.campaign), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
