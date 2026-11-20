#!/usr/bin/env python3
"""Independent scoring of frozen blind regional receiver predictions."""

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

WGS84_A_KM = 6378.137
WGS84_E2 = 0.0066943799901413165
MEAN_RADIUS_KM = 6371.0088
TILE_HALF_WIDTH_KM = 12.5
GEOMETRY_TOLERANCE_KM = 1e-9
Point = tuple[float, float]


@dataclass(frozen=True)
class Decision:
    status: str
    region: str | None = None
    point: Point | None = None
    reason: str | None = None


def distance_km(a: Point, b: Point) -> float:
    lat_a, lat_b = math.radians(a[0]), math.radians(b[0])
    dlon = math.radians(math.remainder(b[1] - a[1], 360))
    chord = math.sin((lat_b - lat_a) / 2) ** 2
    chord += math.cos(lat_a) * math.cos(lat_b) * math.sin(dlon / 2) ** 2
    return 2 * MEAN_RADIUS_KM * math.asin(math.sqrt(min(1.0, chord)))


def surface_ecef(lat: float, lon: float) -> tuple[float, float, float]:
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    radius = WGS84_A_KM / math.sqrt(1 - WGS84_E2 * sin_lat**2)
    return (
        radius * cos_lat * math.cos(lon),
        radius * cos_lat * math.sin(lon),
        radius * (1 - WGS84_E2) * sin_lat,
    )


def tile_contains(center: Point, point: Point) -> bool:
    lat, lon = map(math.radians, center)
    target = surface_ecef(*map(math.radians, point))
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    east_axis = (-sin_lon, cos_lon, 0.0)
    north_axis = (-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat)
    up_axis = (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)
    displacement = tuple(t - c for t, c in zip(target, surface_ecef(lat, lon), strict=True))
    edge = TILE_HALF_WIDTH_KM + GEOMETRY_TOLERANCE_KM
    return (
        math.sumprod(target, up_axis) > 0
        and abs(math.sumprod(displacement, east_axis)) <= edge
        and abs(math.sumprod(displacement, north_axis)) <= edge
    )


def point_from(value: object, label: str) -> Point:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{label} must be [latitude, longitude]")
    for coordinate, limit in zip(value, (90, 180), strict=True):
        if type(coordinate) not in (int, float) or not -limit <= coordinate <= limit:
            raise ValueError(f"invalid coordinate in {label}")
    return float(value[0]), float(value[1])


def string_from(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_from(value: object, label: str) -> str:
    digest = string_from(value, label)
    if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
        raise ValueError(f"{label} must be a SHA-256 digest")
    return digest.lower()


def read_json(path: Path) -> tuple[dict, str]:
    raw = path.read_bytes()
    document = json.loads(raw)
    if not isinstance(document, dict):
        raise ValueError(f"expected an object in {path}")
    return document, sha256(raw)


def index_cases(document: dict, label: str, ids: list[str]) -> dict[str, dict]:
    indexed = {}
    if not isinstance(document["cases"], list):
        raise ValueError(f"{label} cases must be a list")
    for case in document["cases"]:
        case_id = string_from(case["id"], f"{label} id")
        if case_id in indexed:
            raise ValueError(f"duplicate {label} id {case_id}")
        indexed[case_id] = case
    missing, extra = set(ids) - indexed.keys(), indexed.keys() - set(ids)
    if missing or extra:
        raise ValueError(f"{label} id mismatch: missing={sorted(missing)}, extra={sorted(extra)}")
    return indexed


def nonnegative(value: object, label: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{label} must be finite and nonnegative")
    return float(value)


def load_prediction(prediction: dict, regions: dict[str, Point]) -> tuple[dict, dict]:
    status = prediction["status"]
    reason = string_from(prediction["reason"], "prediction reason")
    region, point = prediction["region_id"], prediction["latlon"]
    if status == "fix":
        receiver = Decision(
            status, string_from(region, "published region"), point_from(point, "fix"), reason
        )
    elif status == "withheld" and region is None and point is None:
        receiver = Decision(status, reason=reason)
    else:
        raise ValueError(
            "status must be 'fix' with a region and coordinate, or 'withheld' with neither"
        )

    best_region, best_point = prediction["best_region"], prediction["best_latlon"]
    if best_region is not None:
        string_from(best_region, "best region")
        if best_point is None:
            raise ValueError("best region requires a best coordinate")
    if best_point is not None:
        best_point = point_from(best_point, "best coordinate")
    forced = Decision("fix", best_region, best_point) if best_point else Decision("no_estimate")
    forced_center = (
        Decision("fix", best_region, regions.get(best_region))
        if best_region is not None
        else Decision("no_estimate")
    )

    diagnostics = prediction["diagnostics"]
    if not isinstance(diagnostics, dict):
        raise ValueError("prediction diagnostics must be an object")
    gate = diagnostics.get("region_result")
    region_only = Decision("unavailable")
    if gate is not None:
        gate_status, gate_region = gate["status"], gate["region_id"]
        gate_reason = string_from(gate["reason"], "regional gate reason")
        if gate_status == "accepted":
            string_from(gate_region, "accepted regional gate region")
            region_only = Decision("fix", gate_region, regions.get(gate_region), gate_reason)
        elif gate_status == "withheld" and gate_region is None:
            region_only = Decision("withheld", reason=gate_reason)
        else:
            raise ValueError("regional gate must be 'accepted' with a region or 'withheld'")

    first_region = next(iter(regions))
    candidates = list(regions.values())
    medoid = min(candidates, key=lambda p: (math.fsum(distance_km(p, q) for q in candidates), p))
    medoid_ids = [
        region_id
        for region_id, center in regions.items()
        if distance_km(center, medoid) <= GEOMETRY_TOLERANCE_KM
    ]
    return {
        "receiver": receiver,
        "region_only": region_only,
        "forced_rf": forced,
        "forced_region_center": forced_center,
        "prior_first": Decision("fix", first_region, regions[first_region]),
        "prior_medoid": Decision("fix", medoid_ids[0] if len(medoid_ids) == 1 else None, medoid),
        "always_withhold": Decision("withheld"),
    }, diagnostics


def score_decision(
    decision: Decision, regions: dict[str, Point], truth: Point, correct: str | None
) -> dict:
    point = decision.point
    containing = sorted(
        region
        for region, center in regions.items()
        if point is not None and tile_contains(center, point)
    )
    valid = decision.region in containing if decision.region is not None else bool(containing)
    error = distance_km(point, truth) if point is not None else None
    correct_region = correct is not None and decision.region == correct and valid
    close = error is not None and error <= 5
    return {
        "status": decision.status,
        "reason": decision.reason,
        "region_id": decision.region,
        "latitude": point[0] if point is not None else None,
        "longitude": point[1] if point is not None else None,
        "containing_regions": "|".join(containing),
        "geometry_valid": valid if decision.status == "fix" else None,
        "correct_region": correct_region,
        "error_km": error,
        "position_within_5km": close,
        "joint_within_5km": correct_region and close,
    }


def score_query(query: dict, truth: dict, prediction: dict, query_digest: str) -> dict:
    regions = {}
    for region in query["regions"]:
        region_id = string_from(region["id"], "offered region id")
        if region_id in regions:
            raise ValueError(f"duplicate offered region {region_id}")
        regions[region_id] = point_from(region["center"], f"center of {region_id}")
    if not regions:
        raise ValueError("query must offer at least one region")

    location = point_from(truth["latlon"], "truth coordinate")
    condition, true_region = truth["condition"], truth["true_region"]
    containing = [
        region_id for region_id, center in regions.items() if tile_contains(center, location)
    ]
    if condition == "present" and (true_region is None or containing != [true_region]):
        raise ValueError("present truth must be inside exactly its designated offered tile")
    if condition == "missing" and (true_region is not None or containing):
        raise ValueError("missing truth must lie outside every offered tile")
    if condition not in ("present", "missing"):
        raise ValueError(f"unknown truth condition {condition}")

    decisions, diagnostics = load_prediction(prediction, regions)
    results = {
        policy: score_decision(decision, regions, location, true_region)
        for policy, decision in decisions.items()
    }
    published_region = decisions["receiver"].region
    center_error = (
        distance_km(regions[published_region], location) if published_region in regions else None
    )
    region_only = decisions["region_only"]
    gate_consistent = None
    if published_region is not None and region_only.status != "unavailable":
        gate_consistent = region_only.status == "fix" and region_only.region == published_region
    return {
        "id": truth["id"],
        "pair": string_from(truth["pair"], "truth pair"),
        "site_group": string_from(truth["site_group"], "truth site group"),
        "source": string_from(truth["source"], "truth source"),
        "condition": condition,
        "difficulty": string_from(truth["difficulty"], "truth difficulty"),
        "true_region": true_region,
        "observations_sha256": digest_from(query["observation"], "observation digest"),
        "catalog_sha256": digest_from(query["catalog"], "catalog digest"),
        "query_sha256": query_digest,
        "wall_s": nonnegative(prediction["wall_s"], "case wall time"),
        "published_center_error_km": center_error,
        "published_region_gate_consistent": gate_consistent,
        "decisions": results,
        "diagnostics": diagnostics,
        "truth_point": location,
    }


def fraction(count: int, denominator: int) -> dict:
    return {
        "count": count,
        "denominator": denominator,
        "rate": count / denominator if denominator else None,
    }


def quantile(ordered: list[float], q: float) -> float:
    rank = (len(ordered) - 1) * q
    lo, hi = math.floor(rank), math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def distribution(values) -> dict:
    ordered = sorted(values)
    if not ordered:
        return {"n": 0, "median": None, "p90": None, "worst": None}
    return {
        "n": len(ordered),
        "median": quantile(ordered, 0.5),
        "p90": quantile(ordered, 0.9),
        "worst": ordered[-1],
    }


def policy_summary(rows: list[dict], policy: str, condition: str) -> dict:
    decisions = [row["decisions"][policy] for row in rows if row["condition"] == condition]
    fixes = [decision for decision in decisions if decision["status"] == "fix"]
    errors = [fix["error_km"] for fix in fixes if fix["error_km"] is not None]
    out = {
        "attempts": len(decisions),
        "status_counts": dict(sorted(Counter(d["status"] for d in decisions).items())),
        "publications": fraction(len(fixes), len(decisions)),
        "published_error_km": distribution(errors),
        "published_without_coordinate": len(fixes) - len(errors),
        "published_geometry_violations": sum(not fix["geometry_valid"] for fix in fixes),
        "published_error_at_least_10km": fraction(sum(error >= 10 for error in errors), len(fixes)),
    }
    if condition == "present":
        correct = sum(fix["correct_region"] for fix in fixes)
        out.update(
            correct_region_all_attempts=fraction(correct, len(decisions)),
            correct_region_given_publication=fraction(correct, len(fixes)),
            position_within_5km_all_attempts=fraction(
                sum(fix["position_within_5km"] for fix in fixes), len(decisions)
            ),
            joint_within_5km_all_attempts=fraction(
                sum(fix["joint_within_5km"] for fix in fixes), len(decisions)
            ),
        )
    else:
        out.update(
            rejections=fraction(sum(d["status"] == "withheld" for d in decisions), len(decisions)),
            false_publications=fraction(len(fixes), len(decisions)),
        )
    return out


def summarize(rows: list[dict], policies: tuple[str, ...]) -> dict:
    present_with_centers = [
        row
        for row in rows
        if row["condition"] == "present" and row["published_center_error_km"] is not None
    ]
    center = [row["published_center_error_km"] for row in present_with_centers]
    exact = [row["decisions"]["receiver"]["error_km"] for row in present_with_centers]
    return {
        "published_region_gate_violations": sum(
            row["published_region_gate_consistent"] is False for row in rows
        ),
        "by_policy": {
            policy: {
                condition: policy_summary(rows, policy, condition)
                for condition in ("present", "missing")
            }
            for policy in policies
        },
        "same_published_region_center_comparison_present": {
            "exact_error_km": distribution(exact),
            "center_error_km": distribution(center),
            "exact_minus_center_error_km": distribution(
                x - c for x, c in zip(exact, center, strict=True)
            ),
            "exact_closer": sum(x < c for x, c in zip(exact, center, strict=True)),
        },
    }


def grouped(rows: list[dict], key: str) -> list[tuple[str, list[dict]]]:
    buckets = defaultdict(list)
    for row in rows:
        buckets[row[key]].append(row)
    return sorted(buckets.items())


def pair_summary(rows: list[dict], *, include_rows: bool = False) -> dict:
    counters = Counter()
    details = []
    for pair, members in grouped(rows, "pair"):
        by_condition = {row["condition"]: row for row in members}
        if len(by_condition) != len(members):
            raise ValueError(f"pair {pair} repeats a condition")
        present, missing = by_condition.get("present"), by_condition.get("missing")
        if present is None or missing is None:
            counters["incomplete_pairs"] += 1
            details.append({"pair": pair, "ids": [row["id"] for row in members], "matched": False})
            continue
        match = {
            key: present[key] == missing[key]
            for key in ("observations_sha256", "catalog_sha256", "source", "site_group")
        }
        match["truth_point"] = (
            distance_km(present["truth_point"], missing["truth_point"]) <= GEOMETRY_TOLERANCE_KM
        )
        present_decision, missing_decision = (
            row["decisions"]["receiver"] for row in (present, missing)
        )
        matched = all(match.values())
        details.append(
            {
                "pair": pair,
                "present_id": present["id"],
                "missing_id": missing["id"],
                "matched": matched,
                "match_checks": match,
                "present_status": present_decision["status"],
                "present_correct_region": present_decision["correct_region"],
                "missing_status": missing_decision["status"],
            }
        )
        if matched:
            counters["matched_pairs"] += 1
            counters[
                f"present_{present_decision['status']}_missing_{missing_decision['status']}"
            ] += 1
            if present_decision["correct_region"] and missing_decision["status"] == "withheld":
                counters["correct_region_and_reject"] += 1
                if present_decision["joint_within_5km"]:
                    counters["joint_within_5km_and_reject"] += 1
        else:
            counters["mismatched_complete_pairs"] += 1
    labels = (
        "matched_pairs",
        "incomplete_pairs",
        "mismatched_complete_pairs",
        "present_fix_missing_fix",
        "present_fix_missing_withheld",
        "present_withheld_missing_fix",
        "present_withheld_missing_withheld",
        "correct_region_and_reject",
        "joint_within_5km_and_reject",
    )
    out = {"pairs": len(details), **{label: counters[label] for label in labels}}
    if include_rows:
        out["details"] = details
    return out


def resource_summary(rows: list[dict]) -> dict:
    out = {"receiver_wall_s": distribution(row["wall_s"] for row in rows)}
    for field in ("stage_seconds", "work"):
        values = defaultdict(list)
        for row in rows:
            recorded = row["diagnostics"].get(field, {})
            if not isinstance(recorded, dict):
                raise ValueError(f"query {row['id']} diagnostics {field} must be an object")
            for label, value in recorded.items():
                values[label].append(nonnegative(value, f"{field}.{label}"))
        out[field] = {label: distribution(samples) for label, samples in sorted(values.items())}
    return out


def site_summary(rows: list[dict], policies: tuple[str, ...]) -> dict:
    sites = []
    for name, members in grouped(rows, "site_group"):
        sites.append(
            {"site_group": name, **summarize(members, policies), "pairs": pair_summary(members)}
        )
    medians = [
        site["by_policy"]["receiver"]["present"]["published_error_km"]["median"] for site in sites
    ]
    return {
        "groups": len(sites),
        "groups_without_present_publication": sum(median is None for median in medians),
        "descriptive_distribution_of_site_medians_km": distribution(
            m for m in medians if m is not None
        ),
        "details": sites,
    }


def evaluate(public: Path, truth_path: Path, prediction_path: Path) -> tuple[dict, list[dict]]:
    manifest, manifest_digest = read_json(public / "manifest.json")
    ids = manifest["queries"]
    if not isinstance(ids, list) or not ids:
        raise ValueError("manifest queries must be a nonempty list")
    if any(
        not isinstance(i, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", i) for i in ids
    ):
        raise ValueError("manifest query IDs must be safe filename stems")
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate IDs in manifest queries")
    truth_doc, truth_digest = read_json(truth_path)
    predictions, predictions_digest = read_json(prediction_path)
    truth = index_cases(truth_doc, "truth", ids)
    predicted = index_cases(predictions, "prediction", ids)
    public_files = {"manifest.json": manifest_digest}
    rows = []
    for case_id in ids:
        relative_path = f"queries/{case_id}.json"
        query, query_digest = read_json(public / relative_path)
        if query["id"] != case_id:
            raise ValueError(f"query ID mismatch in {relative_path}")
        public_files[relative_path] = query_digest
        try:
            rows.append(score_query(query, truth[case_id], predicted[case_id], query_digest))
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"query {case_id}: {error}") from error

    policies = tuple(rows[0]["decisions"])
    summary = {
        "schema_version": 1,
        "query_count": len(rows),
        "provenance": {
            "engine_sha256": digest_from(predictions["engine_sha256"], "engine source digest"),
            "predictions_sha256": predictions_digest,
            "truth_sha256": truth_digest,
            "public_manifest_sha256": manifest_digest,
            "public_scoring_input_sha256": sha256(
                json.dumps(public_files, sort_keys=True, separators=(",", ":")).encode()
            ),
            "scorer_sha256": sha256(Path(__file__).read_bytes()),
        },
        "overall": summarize(rows, policies),
        "pairs": pair_summary(rows, include_rows=True),
        "by_site_group": site_summary(rows, policies),
        "by_source": {
            source: {
                **summarize(members, policies),
                "pairs": pair_summary(members),
                "by_site_group": site_summary(members, policies),
                "resources": resource_summary(members),
            }
            for source, members in grouped(rows, "source")
        },
        "missing_by_difficulty": {
            difficulty: {policy: policy_summary(members, policy, "missing") for policy in policies}
            for difficulty, members in grouped(
                [row for row in rows if row["condition"] == "missing"], "difficulty"
            )
        },
        "resources": resource_summary(rows),
    }
    return summary, rows


def write_outputs(output: Path, summary: dict, rows: list[dict]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    with (output / "summary.json").open("w", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write("\n")
    records = []
    for row in rows:
        record = {
            key: value
            for key, value in row.items()
            if key not in ("decisions", "diagnostics", "truth_point")
        }
        for policy, decision in row["decisions"].items():
            record.update({f"{policy}_{key}": value for key, value in decision.items()})
        records.append(record)
    with (output / "per_query.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--predictions", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        summary, rows = evaluate(args.public, args.truth, args.predictions)
        write_outputs(args.output, summary, rows)
    except (KeyError, TypeError, ValueError, OSError) as error:
        parser.exit(2, f"scoring failed: {error}\n")
    print(f"Scored {len(rows)} queries into {args.output}")


if __name__ == "__main__":
    main()
