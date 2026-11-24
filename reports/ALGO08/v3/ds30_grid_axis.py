"""Audit archived weak axes against paired outcomes without fitting positions."""

import argparse
from collections import Counter
import json
from math import acos, atan2, cos, degrees, fsum, hypot, isfinite, pi, radians, sin
from pathlib import Path
from random import Random
from statistics import median

from .ds30_grid_triage import (
    ARMS, AUDITED, CAMPAIGN, DEVELOPMENT, OFFER, RAW_FIELDS, REFERENCE, case_group, checked, digest,
    grid_information, roster, snapshot_inputs, verified_attempt, verified_capture, verified_overlay,
)
from .ds30_position_moments import east_north_km


SOURCE = Path(__file__)
PROTOCOL = SOURCE.with_name("ds30-grid-axis-protocol.md")
RADIUS_KM = 6371.0088
MIN_KM = 0.05
ISOTROPY_GAP = 0.10
PERMUTATIONS = 9_999
SEED = 20261124


def dot(a, b):
    return fsum(x*y for x, y in zip(a, b, strict=True))


def basis(point):
    lat, lon = map(radians, point)
    clat, slat, clon, slon = cos(lat), sin(lat), cos(lon), sin(lon)
    return ((clat*clon, clat*slon, slat), (-slon, clon, 0.), (-slat*clon, -slat*slon, clat))


def transport(vector, start, end):
    """Parallel transport the endpoint EN vector to another EN tangent basis."""
    p, pe, pn = basis(start)
    q, qe, qn = basis(end)
    if 1 + dot(p, q) < 1e-12:
        raise ValueError("Unresolved transport near the antipode")
    v = tuple(vector[0]*a + vector[1]*b for a, b in zip(pe, pn, strict=True))
    scale = dot(v, q)/(1 + dot(p, q))
    rotated = tuple(a-scale*(b+c) for a, b, c in zip(v, p, q, strict=True))
    return dot(rotated, qe), dot(rotated, qn)


def axis_in_metric(ee, nn, en, at_latitude, region_latitude):
    """Transform the archived quadratic into the endpoint tangent metric."""
    sx = RADIUS_KM*pi/180*cos(radians(at_latitude))/(111.32*cos(radians(region_latitude)))
    sy = RADIUS_KM*pi/180/111.
    ee, nn, en = ee/sx**2, nn/sy**2, en/(sx*sy)
    gap = hypot(ee-nn, 2*en)
    low, high = (ee+nn-gap)/2, (ee+nn+gap)/2
    values = dict(curvatures_per_km2=[low, high])
    if not all(isfinite(v) for v in (low, high)) or low <= 0:
        return values | dict(state="nonpositive_curvature")
    if gap <= ISOTROPY_GAP*high:
        return values | dict(state="isotropic")
    major = atan2(2*en, ee-nn)/2
    return values | dict(state="valid", axis=(-sin(major), cos(major)))


def weak_axis(grid, arm):
    x, y = grid["endpoints"][arm]
    point = grid["endpoint_latlon"][arm]
    rows = {(row["east_km"], row["north_km"]): row for row in grid["points"]}
    if (x, y) not in rows or rows[x, y]["latlon"] != point:
        return dict(state="unbound_endpoint")
    step = .5
    selected = {(i, j): rows.get((x+i*step, y+j*step), {}).get("scores", {}).get(arm)
                for i in (-1, 0, 1) for j in (-1, 0, 1)}
    if any(value is None or not isfinite(value) for value in selected.values()):
        return dict(state="missing_stencil")
    s = selected
    ee = (s[1, 0]+s[-1, 0]-2*s[0, 0])/step**2
    nn = (s[0, 1]+s[0, -1]-2*s[0, 0])/step**2
    en = (s[1, 1]-s[-1, 1]-s[1, -1]+s[-1, -1])/(4*step**2)
    result = axis_in_metric(ee, nn, en, point[0], grid["region_center"][0])
    if result["state"] == "valid":
        result["axis"] = transport(result["axis"], point, grid["region_center"])
    return result


def grid_axes(attempt, root, offer):
    proof = grid_information(attempt, root, offer)
    out = dict(state=proof["state"], grid_sha256=proof["grid_file_sha256"])
    if proof["state"] != "bound":
        return out | dict(arms={arm: {"state": proof["state"]} for arm in ARMS})
    run = attempt["evidence"]["receipt"]["run_id"]
    path = root/"fast-scan-standard-v2"/run/"final-error-v7"/"position-grid.json"
    document = json.loads(checked(path, proof["grid_file_sha256"]))["document"]
    return out | dict(arms={arm: weak_axis(document, arm) for arm in ARMS})


def inputs(snapshot, cohort):
    entries, rows, offer, seal, pins = snapshot_inputs(snapshot, cohort)
    return entries, rows, offer, seal, pins | dict(axis_source=digest(SOURCE.read_bytes()), axis_protocol=digest(PROTOCOL.read_bytes()))


def predict(campaign, snapshot, cohort):
    entries, rows, offer, seal, pins = inputs(snapshot, cohort)
    overlay = verified_overlay(campaign, seal) if cohort == "first24" else None
    predictions = []
    for entry in entries:
        case = entry["case"]
        if case == DEVELOPMENT:
            predictions.append(dict(case=case, state="reserved_for_development"))
            continue
        group = case_group(campaign, entry, rows[case], overlay)
        if group is None:
            predictions.append(dict(case=case, state="pair_pending"))
            continue
        row = rows[case]["successor"]
        candidate, root = verified_attempt(campaign, group, row)
        predictions.append(dict(case=case, pair=group[2], candidate=row["attempt_result_sha256"]) |
                           grid_axes(candidate, root, offer))
    return dict(cohort=cohort, pins=pins, rows=predictions)


def double_direction(value):
    length = hypot(*value)
    x, y = (coordinate/length for coordinate in value)
    return x*x-y*y, 2*x*y


def angular_null(axes, bearings):
    """Preserve the exact signed axial geometry of the observed margins."""
    n = len(axes)

    def mean_vectors(vectors):
        return tuple(fsum(column)/n for column in zip(*vectors, strict=True))

    mean_axis, mean_bearing = mean_vectors(axes), mean_vectors(bearings)
    observed = fsum(dot(x, y) for x, y in zip(axes, bearings, strict=True))/n
    out = dict(mean_cos2=observed, exact_null_mean=dot(mean_axis, mean_bearing),
               axis_concentration=hypot(*mean_axis), bearing_concentration=hypot(*mean_bearing))
    if n < 2:
        return out | dict(null_middle_95=None, upper_tail_rank=None)
    matrix = [[dot(a, b) for b in bearings] for a in axes]
    random = Random(SEED)
    order = list(range(n))
    draws = []
    for _ in range(PERMUTATIONS):
        random.shuffle(order)
        draws.append(fsum(scores[j] for scores, j in zip(matrix, order, strict=True))/n)
    draws.sort()
    return out | dict(null_middle_95=[draws[int(q*(len(draws)-1))] for q in (.025, .975)],
                      upper_tail_rank=(1+sum(x >= observed-1e-12 for x in draws))/(1+len(draws)))


def displacement(origin, destination, centre):
    return transport(east_north_km(origin, destination), origin, centre)


def bearing_stats(axes, vectors):
    if not axes:
        return dict(n=0)
    unit_axes = [double_direction(x) for x in axes]
    bearings = [double_direction(v) for v in vectors]
    acute = [degrees(acos(max(-1., min(1., dot(x, y))))/2) for x, y in zip(unit_axes, bearings, strict=True)]
    residuals = [abs(a[0]*v[1]-a[1]*v[0])/hypot(*a) for a, v in zip(axes, vectors, strict=True)]
    return dict(n=len(axes), median_acute_deg=median(acute), within_30deg=sum(angle <= 30. for angle in acute),
                median_displacement_km=median(map(hypot_from_pair, vectors)), median_perpendicular_km=median(residuals),
                **angular_null(unit_axes, bearings))


def hypot_from_pair(value):
    return hypot(*value)


def centered(vectors):
    east, north = (fsum(column)/len(vectors) for column in zip(*vectors, strict=True))
    return [(x-east, y-north) for x, y in vectors], hypot(east, north)


def analyze(rows, arm, target):
    selected = []
    exclusions = Counter()
    for row in rows:
        value = row["arms"][arm]
        a, b = value["candidate_axis"], value["installed_axis"]
        v = value[target]
        if v is None:
            exclusions["no_shared_fix" if target == "to_installed" else "no_scored_candidate_fix"] += 1
        elif hypot(*v) < MIN_KM:
            exclusions["short_displacement"] += 1
        elif a["state"] != "valid":
            exclusions["candidate_"+a["state"]] += 1
        else:
            selected.append((a["axis"], b.get("axis"), v))
    candidate = [a for a, _, _ in selected]
    vectors = [v for _, _, v in selected]
    metrics = bearing_stats(candidate, vectors)
    common = [(a, b, v) for a, b, v in selected if b is not None]
    out = dict(assigned=len(rows), exclusions=dict(exclusions), candidate=metrics,
               installed_unresolved=len(selected)-len(common))
    if not selected:
        return out
    rem, mean = centered(vectors)
    retained = [(a, v) for a, v in zip(candidate, rem, strict=True) if hypot(*v) >= MIN_KM]
    out.update(mean_vector_magnitude_km=mean, centered_exclusions=len(rem)-len(retained),
               centered_candidate=bearing_stats([a for a, _ in retained], [v for _, v in retained]))
    if common:
        a, b, v = map(list, zip(*common, strict=True))
        disagreement = [degrees(acos(max(-1., min(1., dot(double_direction(u), double_direction(w)))))/2)
                        for u, w in zip(a, b, strict=True)]
        out["matched"] = dict(candidate=metrics if len(common) == len(selected) else bearing_stats(a, v),
                              installed=bearing_stats(b, v), median_axis_disagreement_deg=median(disagreement))
        matched_rem, _ = centered(v)
        joined = [(x, y, z) for x, y, z in zip(a, b, matched_rem, strict=True) if hypot(*z) >= MIN_KM]
        out["matched_centered"] = dict(
            candidate=out["centered_candidate"] if len(common) == len(selected)
            else bearing_stats([x for x, _, _ in joined], [z for _, _, z in joined]),
            installed=bearing_stats([y for _, y, _ in joined], [z for _, _, z in joined]))
    return out


def score(campaign, snapshot, path, pin):
    prediction = json.loads(checked(path, pin))
    cohort = prediction["cohort"]
    entries, rows, offer, seal, pins = inputs(snapshot, cohort)
    marks = prediction["rows"]
    if prediction["pins"] != pins or [r["case"] for r in marks] != [entry["case"] for entry in entries]:
        raise ValueError("Axis prediction does not bind the frozen snapshot")
    pending = [r["case"] for r in marks if r["state"] == "pair_pending"]
    if cohort == "next3" and pending:
        return dict(cohort=cohort, prediction=pin, pending=pending)
    overlay = verified_overlay(campaign, seal) if cohort == "first24" else None
    assigned = roster()
    outcomes = {}
    joints = []
    for mark, entry in zip(marks, entries, strict=True):
        case = entry["case"]
        if mark["state"] in ("pair_pending", "reserved_for_development"):
            outcomes[case] = dict(status=mark["state"])
            continue
        group = case_group(campaign, entry, rows[case], overlay)
        if group[2] != mark["pair"] or rows[case]["successor"]["attempt_result_sha256"] != mark["candidate"]:
            raise ValueError("Axis prediction does not bind the verified worker")
        stock, stock_root = verified_attempt(campaign, group, rows[case]["installed"])
        candidate, _ = verified_attempt(campaign, group, rows[case]["successor"])
        stock_input, candidate_input = (run["raw_identity"] for run in (stock, candidate))
        if any(stock_input[key] != candidate_input[key] for key in (*RAW_FIELDS, "region_sha256")):
            outcomes[case] = dict(status="unmatched_raw_or_offer")
            continue
        if candidate_input["region_sha256"].removeprefix("sha256:") != OFFER:
            outcomes[case] = dict(status="different_offer")
            continue
        verified_capture(campaign, entry, rows[case], assigned[case], overlay)
        installed_axes = grid_axes(stock, stock_root, offer)
        reference = assigned[case]["reference"]
        data = {}
        for arm in ARMS:
            start = candidate["evidence"]["arms"][arm].get("latlon")
            finish = stock["evidence"]["arms"][arm].get("latlon")
            data[arm] = dict(candidate_axis=mark["arms"][arm], installed_axis=installed_axes["arms"][arm],
                             to_installed=displacement(start, finish, offer["center"]) if start and finish else None,
                             to_survey=displacement(start, reference, offer["center"]) if start and reference else None)
        joints.append(dict(case=case, arms=data))
        outcomes[case] = dict(status="matched", candidate=candidate["outcome"], installed=stock["outcome"],
                             prior_geometry=case in AUDITED, installed_grid_sha256=installed_axes["grid_sha256"],
                             axes={arm: {key: row[key]["state"] for key in ("candidate_axis", "installed_axis")}
                                   for arm, row in data.items()})
    return dict(cohort=cohort, prediction=pin, reference=REFERENCE, outcomes=outcomes,
                to_installed={arm: analyze(joints, arm, "to_installed") for arm in ARMS},
                omit_prior_geometry={arm: analyze([r for r in joints if r["case"] not in AUDITED], arm, "to_installed")
                                     for arm in ARMS},
                to_survey={arm: analyze(joints, arm, "to_survey") for arm in ARMS})


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
