"""Rank candidate-only position-grid information, then score sealed raw pairs."""

import argparse
from collections import Counter
from itertools import combinations
import json
from math import fsum, isfinite, sqrt
from pathlib import Path
from statistics import median

from leo.contracts.position_grid import validate

from .ds30_anchor_direction import SCALE, canonical, scientific_grid, stencil
from .ds30_centered_error import selected_rows, verified_capture, verified_overlay
from .ds30_oracle_routing import CAMPAIGN, PLAN, RELOCATION, checked, digest, frozen_order
from .full_successor_score import ARMS, BUILDS, OFFER, PINS, REFERENCE, paired_rows, roster


DEVELOPMENT = "DS30-0049"
AUDITED = ("DS30-0086", "DS30-0220")
PROSPECTIVE = ("DS30-0010", "DS30-0444", "DS30-0073")
CURVATURE_LIMIT = 2 * SCALE  # The quadratic delta at 1 km is half the curvature.
SOURCE = Path(__file__)
PROTOCOL = SOURCE.with_name("ds30-grid-triage-protocol.md")
RAW_FIELDS = ("archive_sha256", "causal_cutoff_utc_ns", "inventory_sha256",
              "raw_authority_sha256", "session_id", "window_count")


def snapshot_inputs(snapshot, cohort):
    plan = json.loads(checked(snapshot/"plan.json", PLAN))
    offer = json.loads(checked(snapshot/"offer.json", "sha256:"+OFFER))
    seal_bytes = (snapshot/"rows-with-relocations-seal.json").read_bytes()
    seal = json.loads(seal_bytes)
    order = frozen_order(plan)
    if (seal["plan_sha256"] != PLAN or order[23]["case"] != "DS30-0147"
            or tuple(e["case"] for e in order[24:27]) != PROSPECTIVE):
        raise ValueError("Snapshot does not bind the frozen assignments")
    entries = order[:24] if cohort == "first24" else order[24:27]
    body = checked(snapshot/"rows-with-relocations.jsonl", seal["combined_sha256"])
    rows = selected_rows(body, tuple(entry["case"] for entry in entries))
    pins = dict(plan=PLAN, offer="sha256:"+OFFER, seal=digest(seal_bytes), combined_export=seal["combined_sha256"],
                sealed_ordinary_export=seal["ledger_snapshot_sha256"], source=digest(SOURCE.read_bytes()),
                protocol=digest(PROTOCOL.read_bytes()))
    return entries, rows, offer, seal, pins


def case_group(campaign, entry, rows, overlay):
    case = entry["case"]
    if set(rows) != set(BUILDS) or any(not row["verified_pair"] for row in rows.values()):
        return None
    holder = campaign / ("relocation" if case == RELOCATION else "cases") / case
    pair_body = (holder/"pair.json").read_bytes()
    pair = json.loads(pair_body)
    if (not pair["verified_pair"] or not pair["chronological"] or pair["state"] != "observed_pair"
            or pair["actual_order"] != entry["order"]
            or (case == RELOCATION and pair != overlay["paired_scope"])):
        raise ValueError(f"Original pair seal differs for {case}")
    return holder, pair, digest(pair_body)


def verified_attempt(campaign, group, row):
    holder, pair, _ = group
    role = row["algorithm"]
    path = campaign / row["attempt"]
    pin = pair["attempt_result_sha256"][role]
    if not path.is_relative_to(holder/role) or path.resolve(strict=True) != path:
        raise ValueError("Attempt path is outside its enrolled case and algorithm")
    parts = path.relative_to(holder/role).parts
    if (len(parts) != 2 or not parts[0].startswith("attempt-") or not parts[0][8:].isdigit()
            or parts[1] not in ("result.json", "revalidation.json") or pin != row["attempt_result_sha256"]
            or row["build_sha256"] != PINS[role] or row["generation"] != pair["generation"]
            or row["authority_sha256"] != pair["authority_sha256"] or not row["acquisition_verified"]):
        raise ValueError(f"Unverified selected field worker at {path}")
    attempt = json.loads(checked(path, pin))
    if (attempt["outcome"] != row["outcome"] or attempt["algorithm"] != role
            or attempt["evidence"]["raw_authority"] != row["raw_authority_sha256"]):
        raise ValueError("The paired worker no longer matches the field export")
    return attempt, path.parent/"publication"


def curvature(grid, arm):
    x, y = grid["endpoints"][arm]
    points = {(r["east_km"], r["north_km"]): r["scores"][arm] for r in grid["points"]}
    estimate = stencil(points, x, y, 0.5, 1., 0.)
    return None if estimate is None else estimate["principal_curvatures"][0]


def grid_information(attempt, root, offer):
    def unavailable(state):
        return dict(state=state, information=dict.fromkeys(ARMS), grid_file_sha256=None)

    if attempt["outcome"] != "complete":
        return unavailable(attempt["outcome"])
    evidence = attempt["evidence"]
    receipt = evidence["receipt"]
    if receipt["region"] != offer or attempt["raw_identity"]["region_sha256"].removeprefix("sha256:") != OFFER:
        return unavailable("different_offer")
    sealed_science = evidence.get("scientific_digests", {}).get("grid")
    if sealed_science is None:
        return unavailable("no_signed_grid_digest")
    run = receipt["run_id"]
    folder = root/"fast-scan-standard-v2"/run/"final-error-v7"
    path = folder/"position-grid.json"
    try:
        body = path.read_bytes()
        manifest = json.loads((folder/"manifest.json").read_bytes())
        doc = json.loads(body)
        grid = validate(doc["document"], manifest)
        binding = grid["binding"]
        position = next(x["sha256"] for x in evidence["artifacts"] if x["name"] == "position")
        terminal = json.loads(checked(root/"fast-scan-automatic-work"/run/"terminal.json", receipt["terminal_sha256"]))
        if (not grid["complete"] or doc["sha256"] != canonical(grid)
                or sealed_science != canonical(scientific_grid(grid))
                or binding["run_id"] != run or binding["owner_sha256"] != evidence["owners"]
                or binding["input_sha256"] != attempt["native_sha256"]
                or binding["terminal_sha256"] != receipt["terminal_sha256"]
                or binding["position_png_sha256"] != position
                or manifest["raw_authority"] != evidence["raw_authority"] or manifest["region"] != offer
                or terminal["region"] != offer or terminal["native_sha256"] != attempt["native_sha256"]
                or terminal["decision"] != "ok" or terminal["session_id"] != receipt["session_id"]
                or any(grid["endpoint_latlon"][a] != evidence["arms"][a]["latlon"]
                       or grid["endpoint_latlon"][a] != terminal["arms"][a]["latlon"] for a in ARMS)
                or any(not isfinite(v) or abs(v) > 1e-4 for v in grid["endpoint_objective_replay"].values())):
            return unavailable("unbound_numerical_grid")
    except FileNotFoundError:
        return unavailable("missing_grid_publication")
    except (KeyError, ValueError, TypeError, StopIteration):
        return unavailable("unbound_numerical_grid")
    information = {arm: curvature(grid, arm) for arm in ARMS}
    return dict(state="bound", information=information, grid_file_sha256=digest(body))


def predict(campaign, snapshot, cohort):
    entries, rows, offer, seal, pins = snapshot_inputs(snapshot, cohort)
    overlay = verified_overlay(campaign, seal) if cohort == "first24" else None
    records = []
    for entry in entries:
        case = entry["case"]
        base = dict(case=case, prior_geometry=case in AUDITED)
        if case == DEVELOPMENT:
            records.append(base | dict(state="reserved_for_development"))
            continue
        group = case_group(campaign, entry, rows[case], overlay)
        if group is None:
            records.append(base | dict(state="pair_pending"))
            continue
        candidate = rows[case]["successor"]
        result, root = verified_attempt(campaign, group, candidate)
        records.append(base | grid_information(result, root, offer) |
                       dict(pair=group[2], candidate=candidate["attempt_result_sha256"]))
    return dict(cohort=cohort, pins=pins, rows=records, threshold=CURVATURE_LIMIT)


def tau_b(rows):
    counts = Counter()
    for (x, y), (u, v) in combinations(rows, 2):
        a, b = (x > u)-(x < u), (y > v)-(y < v)
        counts[(a == 0, b == 0, a*b)] += 1
    good, bad = counts[False, False, 1], counts[False, False, -1]
    lines = good + bad
    denominator = sqrt((lines + counts[True, False, 0]) * (lines + counts[False, True, 0]))
    return None if denominator == 0 else (good-bad)/denominator


def fraction_summary(rows):
    return dict(n=len(rows), median_successor_minus_installed_km=median(r["delta"] for r in rows) if rows else None,
                median_successor_km=median(r["successor"] for r in rows) if rows else None,
                median_installed_km=median(r["installed"] for r in rows) if rows else None,
                candidate_worse=sum(r["delta"] > 0 for r in rows), cases=[r["case"] for r in rows])


def ranked(rows, arm):
    measurements = []
    for row in rows:
        info = row["candidate_grid"]["information"][arm]
        a, b = (row[role][arm+"_error_km"] for role in BUILDS)
        if None in (info, a, b):
            continue
        measurements.append(dict(case=row["case"], low_information=-info, delta=b-a, installed=a, successor=b,
                                 installed_information=row["installed_grid"]["information"][arm]))
    ordered = sorted(measurements, key=lambda r: -r["low_information"])
    split = (len(ordered)+2)//3
    ranks = {key: tau_b([(r["low_information"], r[key]) for r in ordered]) for key in ("delta", "installed", "successor")}
    baseline = [(r["low_information"], -r["installed_information"]) for r in ordered
                if r["installed_information"] is not None]
    return dict(n=len(ordered), tau_b=ranks, uncertainty_comparison=dict(n=len(baseline), tau_b=tau_b(baseline)),
                weakest_third=fraction_summary(ordered[:split]), remainder=fraction_summary(ordered[split:]))


def cost_and_fixes(rows):
    def retry(row):
        return any(v is not None and v <= CURVATURE_LIMIT for v in row["candidate_grid"]["information"].values())

    picked = {r["case"] for r in rows if retry(r)}
    if not rows:
        return dict(retried=[], clocks={}, results={})
    clocks = {}
    for scope in ("elapsed_s", "cpu_s"):
        installed = fsum(r["installed"][scope] for r in rows)
        candidate = fsum(r["successor"][scope] for r in rows)
        extra = fsum(r["installed"][scope] for r in rows if r["case"] in picked)
        ratios = [r["successor"][scope]/r["installed"][scope] + (r["case"] in picked) for r in rows]
        clocks[scope] = dict(installed_s=installed, candidate_s=candidate, full_retry_s=extra, total_s=candidate+extra,
                             sum_ratio=(candidate+extra)/installed, median_ratio=median(ratios),
                             mean_retry_budget_s=(installed-candidate)/len(picked) if picked else None,
                             mean_retry_budget_for_half_s=(installed/2-candidate)/len(picked) if picked else None)
    results = {}
    for arm in ARMS:
        values = [(r["installed"][arm+"_error_km"], r["successor"][arm+"_error_km"], r["case"] in picked) for r in rows]
        groups = dict(installed=[a for a, _, _ in values], successor=[b for _, b, _ in values],
                      with_retry=[a if hit else b for a, b, hit in values])
        results[arm] = {key: dict(fixes=sum(v is not None for v in group), within_1km=sum(v is not None and v <= 1 for v in group),
                                  within_2km=sum(v is not None and v <= 2 for v in group),
                                  median_km=median(finite) if (finite := [v for v in group if v is not None]) else None)
                        for key, group in groups.items()}
    return dict(retried=[r["case"] for r in rows if r["case"] in picked], clocks=clocks, results=results)


def score(campaign, snapshot, prediction_path, pin):
    prediction = json.loads(checked(prediction_path, pin))
    cohort = prediction["cohort"]
    entries, rows, offer, seal, pins = snapshot_inputs(snapshot, cohort)
    if (prediction["pins"] != pins or prediction["threshold"] != CURVATURE_LIMIT
            or [r["case"] for r in prediction["rows"]] != [entry["case"] for entry in entries]):
        raise ValueError("Wrong prediction generation or protocol")
    records = []
    statuses = {}
    if cohort == "next3" and any(r["state"] == "pair_pending" for r in prediction["rows"]):
        return dict(cohort=cohort, prediction=pin, pending=[r["case"] for r in prediction["rows"]
                    if r["state"] == "pair_pending"], note="all three prospective pairs required")
    overlay = verified_overlay(campaign, seal) if cohort == "first24" else None
    assigned = roster()
    for prediction_row, entry in zip(prediction["rows"], entries, strict=True):
        case = entry["case"]
        statuses[case] = prediction_row["state"]
        if prediction_row["state"] in ("pair_pending", "reserved_for_development"):
            continue
        group = case_group(campaign, entry, rows[case], overlay)
        if group[2] != prediction_row["pair"] or rows[case]["successor"]["attempt_result_sha256"] != prediction_row["candidate"]:
            raise ValueError("Prediction and published field pair have different custody")
        stock, stock_root = verified_attempt(campaign, group, rows[case]["installed"])
        candidate, _ = verified_attempt(campaign, group, rows[case]["successor"])
        if (any(stock["raw_identity"][key] != candidate["raw_identity"][key] for key in RAW_FIELDS)
                or stock["raw_identity"]["region_sha256"] != candidate["raw_identity"]["region_sha256"]):
            statuses[case] = "unmatched_raw_or_offer"
            continue
        if stock["raw_identity"]["region_sha256"].removeprefix("sha256:") != OFFER:
            statuses[case] = "different_offer"
            continue
        verified_capture(campaign, entry, rows[case], assigned[case], overlay)
        ((a, b),) = paired_rows(rows[case].values(), {case: assigned[case]})
        keep = ("elapsed_s", "cpu_s", "outcome", *(arm+"_error_km" for arm in ARMS))
        records.append(dict(case=case, prior_geometry=prediction_row["prior_geometry"], candidate_grid=prediction_row,
                            installed_grid=grid_information(stock, stock_root, offer),
                            installed={key: a[key] for key in keep}, successor={key: b[key] for key in keep}))
    return dict(cohort=cohort, prediction=pin, reference=REFERENCE, statuses=statuses, records=records,
                outcomes={role: dict(Counter(r[role]["outcome"] for r in records)) for role in BUILDS},
                rank={arm: ranked(records, arm) for arm in ARMS},
                omit_prior_geometry={arm: ranked([r for r in records if not r["prior_geometry"]], arm) for arm in ARMS},
                policy=cost_and_fixes(records))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    parser.add_argument("--cohort", choices=("first24", "next3"), default="first24")
    parser.add_argument("--score", nargs=2, metavar=("PREDICTION", "SHA256"))
    args = parser.parse_args()
    if args.score:
        path, pin = args.score
        result = score(args.campaign, args.snapshot, Path(path), pin)
    else:
        result = predict(args.campaign, args.snapshot, args.cohort)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
