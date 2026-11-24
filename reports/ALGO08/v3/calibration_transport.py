"""Transfer published DS30 calibration vectors without a survey-dependent construction."""

import argparse
from collections import Counter
import json
from math import atan2, cos, degrees, hypot, radians, sin
from pathlib import Path
from statistics import fmean, median

from reports.ALGO08.v3.full_successor_score import (
    ARMS, BUILDS, OFFER, REFERENCE, ROOT, frozen_stage_order, paired_rows, roster,
)
from reports.ALGO08.v3.ds30_paired_inputs import checked, digest
from tools.pipeline_eval.scoring import coordinate, distance_km


HERE = Path(__file__).resolve().parent
FIRST30 = "2994fe3bd068dc661fb7c4a6f9667e370218acae226106f7dd0b05636d71f8c5"
FIRST41 = "32f8c27ab3c088201e4e6f1a2176108341f7582a35f687ddcfabc49e33ccf7aa"
FIELD = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
COMPARISONS = {
    "installed_calibration": ("installed_c0", "installed_fitted_c"),
    "candidate_calibration": ("successor_c0", "successor_fitted_c"),
    "between_builds_c0": ("installed_c0", "successor_c0"),
    "between_builds_fitted": ("installed_fitted_c", "successor_fitted_c"),
    "transfer_vs_candidate_c0": ("successor_c0", "successor_with_installed_delta"),
    "transfer_vs_candidate_fitted": ("successor_fitted_c", "successor_with_installed_delta"),
    "transfer_vs_installed_fitted": ("installed_fitted_c", "successor_with_installed_delta"),
    "reciprocal_vs_installed_fitted": ("installed_fitted_c", "installed_with_successor_delta"),
    "transfer_between_c0_anchors": ("installed_with_successor_delta", "successor_fitted_c"),
}


def sphere_vector(point):
    latitude, longitude = map(radians, coordinate(point))
    return cos(latitude)*cos(longitude), cos(latitude)*sin(longitude), sin(latitude)


def norm(v):
    return hypot(*v)


def scaled(v, scale):
    return tuple(scale*x for x in v)


def cross(a, b):
    x, y, z = a
    p, q, r = b
    return y*r-z*q, z*p-x*r, x*q-y*p


def dot(a, b):
    return sum(x*y for x, y in zip(a, b, strict=True))


def add(a, b):
    return tuple(x+y for x, y in zip(a, b, strict=True))


def spherical_coordinate(v):
    x, y, z = v
    return degrees(atan2(z, hypot(x, y))), degrees(atan2(y, x))


def transfer(source_zero, source_fitted, target_zero):
    """Keep arc length and parallel transport direction between published anchors."""
    start, end, target = map(sphere_vector, (source_zero, source_fitted, target_zero))
    axis = cross(start, end)
    span = norm(axis)
    cosine = dot(start, end)
    if span < 1e-15:
        if cosine < 0:
            raise ValueError("The source correction has no unique shortest arc")
        return tuple(target_zero)
    angle = atan2(span, cosine)
    tangent = scaled(cross(axis, start), 1/span)
    # Minimal 3D rotation along the anchor-to-anchor arc rotates the tangent basis in parallel.
    shift = cross(start, target)
    denominator = 1 + dot(start, target)
    if denominator < 1e-14:
        raise ValueError("The anchors are antipodal or numerically indistinguishable from antipodal")
    carry = cross(shift, tangent)
    transported = add(add(tangent, carry), scaled(cross(shift, carry), 1/denominator))
    return spherical_coordinate(add(scaled(target, cos(angle)), scaled(transported, sin(angle))))


def distance_m(left, right):
    km = distance_km(left, right)
    return None if km is None else 1_000*km


def normalized_arms(evidence):
    return {arm: {key: evidence[arm].get(key) for key in ("latlon", "rf_rms_hz")} for arm in ARMS}


def signed_attempt(campaign, row):
    subpath = Path(row["attempt"])
    case, method = row["case"], row["algorithm"]
    parts = subpath.parts
    if (len(parts) != 5 or parts[:3] != ("cases", case, method) or ".." in parts
            or not parts[3].startswith("attempt-") or parts[4] not in ("result.json", "revalidation.json")):
        raise ValueError("Unexpected saved field attempt path")
    path = campaign / subpath
    if path.resolve(strict=True) != path:
        raise ValueError("Saved field attempt moved outside the enrolled tree")
    result = json.loads(checked(path, row["attempt_result_sha256"]))
    evidence, raw = result["evidence"], result["raw_identity"]
    if (result["algorithm"] != method or result["outcome"] != row["outcome"]
            or result["authority_sha256"] != row["authority_sha256"]
            or raw["raw_authority_sha256"] != row["raw_authority_sha256"]
            or raw["region_sha256"] != "sha256:"+OFFER
            or evidence["receipt"].get("terminal_sha256") != row["terminal_sha256"]
            or normalized_arms(evidence["arms"]) != row["arms"]):
        raise ValueError(f"The verified release endpoints or input binding changed on {case}, {method}")
    return result


def signed_cohort(folder, campaign, count, pin):
    seal = json.loads((folder / "rows-with-relocations-seal.json").read_bytes())
    body = (folder / "rows-with-relocations.jsonl").read_bytes()
    if digest(body) != seal["combined_sha256"] or digest(body) != "sha256:"+pin:
        raise ValueError("The frozen field export changed")
    rows = [r for line in body.splitlines() if (r := json.loads(line))["verified_pair"] is True]
    assigned = roster(ROOT)
    order = frozen_stage_order({c: (x["case_id"], x["physical_content"]) for c, x in assigned.items()})[:count]
    if set(order) != {r["case"] for r in rows}:
        raise ValueError("Verified field rows do not fill the complete assigned prefix")
    paired_rows(rows, {case: assigned[case] for case in order})
    matching = {(r["case"], r["algorithm"]): r for r in rows}
    verified = {}
    for case in order:
        row_pair = {method: matching[case, method] for method in BUILDS}
        a, b = (signed_attempt(campaign, row_pair[method]) for method in BUILDS)
        if (a["raw_identity"] != b["raw_identity"]
                or a["evidence"]["receipt"]["region"] != b["evidence"]["receipt"]["region"]
                or assigned[case]["reference"] is None):
            raise ValueError(f"The paired outputs do not share the original source, offer and site for {case}")
        verified[case] = row_pair
    return verified, {case: assigned[case]["reference"] for case in order}


def endpoints(pair):
    """Generate actual and transported positions with signed endpoints only."""
    points = {f"{method}_{arm}": pair[method]["arms"][arm]["latlon"] for method in BUILDS for arm in ARMS}
    i0, i1, s0, s1 = (points[k] for k in ("installed_c0", "installed_fitted_c", "successor_c0", "successor_fitted_c"))
    shared = i0 is not None and s0 is not None
    points["successor_with_installed_delta"] = list(transfer(i0, i1, s0)) if shared else s1
    points["installed_with_successor_delta"] = list(transfer(s0, s1, i0)) if shared else i1
    return points


def measure_case(pair, reference):
    points = endpoints(pair)
    return dict(state={method: pair[method]["outcome"] for method in BUILDS},
                attempt_sha256={method: pair[method]["attempt_result_sha256"] for method in BUILDS},
                terminal_sha256={method: pair[method]["terminal_sha256"] for method in BUILDS},
                rf_rms_hz={method: {arm: pair[method]["arms"][arm]["rf_rms_hz"] for arm in ARMS}
                           for method in BUILDS},
                position=points, errors_m={k: distance_m(reference, point) for k, point in points.items()},
                displacement_m={method: distance_m(points[method+"_c0"], points[method+"_fitted_c"])
                                for method in BUILDS})


def paired_delta(values):
    valid = [b-a for a, b in values if None not in (a,b)]
    if not valid:
        return dict(n=0, mean=None, median=None, median_abs=None, improved=0, worsened=0, equal=0)
    return dict(n=len(valid), mean=fmean(valid), median=median(valid), median_abs=median(map(abs, valid)),
                improved=sum(x < 0 for x in valid), worsened=sum(x > 0 for x in valid), equal=valid.count(0))


def threshold(changes, limit):
    before, after, gained, lost = [], [], [], []
    for case, (a, b) in changes.items():
        was, is_ = (v is not None and v <= limit for v in (a, b))
        if was:
            before.append(case)
        if is_:
            after.append(case)
        if was and not is_:
            lost.append(case)
        if is_ and not was:
            gained.append(case)
    return dict(before=len(before), after=len(after), gained=gained, lost=lost)


def summary(measurements):
    distance_changes = {}
    for comparison, (old, new) in COMPARISONS.items():
        changes = {case: (m["errors_m"][old], m["errors_m"][new]) for case, m in measurements.items()}
        distance_changes[comparison] = dict(error_delta_m=paired_delta(changes.values()),
                                            coverage={str(limit): threshold(changes, limit) for limit in (1000,2000)})
    rf = {method: paired_delta((m["rf_rms_hz"][method][a] for a in ARMS) for m in measurements.values())
          for method in BUILDS}
    delta = {method: [m["displacement_m"][method] for m in measurements.values() if m["displacement_m"][method] is not None]
             for method in BUILDS}
    return dict(assigned=len(measurements),
                outcomes={method: dict(Counter(m["state"][method] for m in measurements.values())) for method in BUILDS},
                median_calibration_displacement_m={method: median(d) if d else None for method, d in delta.items()},
                contrasts=distance_changes, calibration_rf_delta_hz=rf)


def study(folder, count, prior=None):
    pin = FIRST30 if count == 30 else FIRST41
    pairs, references = signed_cohort(folder, FIELD, count, pin)
    order = list(pairs)
    previous = None
    first30_sha256 = None
    if count == 41:
        body = prior.read_bytes()
        first30_sha256 = digest(body)
        previous = json.loads(body)
        if previous["ledger_sha256"] != FIRST30 or previous["order"] != order[:30]:
            raise ValueError("The previously sealed first-30 outcomes changed")
        for case in order[:30]:
            if any(previous["cases"][case]["attempt_sha256"][method] != pairs[case][method]["attempt_result_sha256"]
                   for method in BUILDS):
                raise ValueError("A previously sealed first-30 attempt changed")
    records = {case: measure_case(pair, references[case]) for case, pair in pairs.items()}
    if previous and any(previous["cases"][case] != records[case] for case in order[:30]):
        raise ValueError("The published first-30 readout no longer reproduces")
    groups = {"first30": order[:30]} if count == 30 else {"later11": order[30:], "entire41": order}
    reports = {}
    for name, cases in groups.items():
        all_ = {c: records[c] for c in cases}
        shared = {c: record for c, record in all_.items() if set(record["state"].values()) == {"complete"}}
        reports[name] = dict(all_attempts=summary(all_), shared_fixes=summary(shared))
    return dict(ledger_sha256=pin, reference_sha256=REFERENCE, first30_readout_sha256=first30_sha256,
                protocol_sha256=digest((HERE/"calibration-transport-protocol.md").read_bytes()),
                order=order, cases=records, reports=reports)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("count", type=int, choices=(30,41))
    parser.add_argument("--first30", type=Path)
    args = parser.parse_args()
    if args.count == 41 and args.first30 is None:
        parser.error("The independently sealed first-30 report is required")
    print(json.dumps(study(args.export, args.count, args.first30), indent=2, sort_keys=True, allow_nan=False))
