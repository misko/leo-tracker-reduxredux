"""Independent structural audit of frozen forecast-only direction support outputs."""

from __future__ import annotations

import ast
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SIN10 = math.sin(math.radians(10.0))
COS10 = math.cos(math.radians(10.0))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(actual, expected, tolerance=1e-12):
    return math.isclose(float(actual), float(expected), rel_tol=tolerance, abs_tol=tolerance)


def lane_key(lane):
    return json.dumps(lane, sort_keys=True, separators=(",", ":"))


def normalized_priors(components):
    logs = [
        -math.inf if component.get("log_prior") is None else float(component["log_prior"])
        for component in components
    ]
    largest = max(logs)
    weights = [0.0 if not math.isfinite(value) else math.exp(value - largest) for value in logs]
    total = math.fsum(weights)
    return [weight / total for weight in weights]


def unique_peak(values):
    maximum = max(values)
    indices = [index for index, value in enumerate(values) if value == maximum]
    if len(indices) != 1:
        return None, "tied_scheduled_peak"
    if indices[0] in (0, len(values) - 1):
        return None, "boundary_scheduled_peak"
    return indices[0], None


def independent_support(times_ns, q, rx0, rx1, visible):
    times_s = [(value - times_ns[0]) / 1e9 for value in times_ns]
    zeros = [index for index, value in enumerate(q) if value == 0]
    plateau = any(right == left + 1 for left, right in zip(zeros, zeros[1:], strict=False))
    events = []
    if not plateau:
        for index in zeros:
            if index not in (0, len(q) - 1) and q[index - 1] * q[index + 1] < 0:
                slope = (q[index + 1] - q[index - 1]) / (
                    times_s[index + 1] - times_s[index - 1]
                )
                events.append((times_s[index], slope, (index - 1, index, index + 1)))
        for index in range(len(q) - 1):
            if q[index] * q[index + 1] < 0:
                slope = (q[index + 1] - q[index]) / (
                    times_s[index + 1] - times_s[index]
                )
                crossing = times_s[index] - q[index] / slope
                events.append((crossing, slope, (index, index + 1)))
    crossing_reason = None
    if plateau:
        crossing_reason = "zero_plateau"
    elif len(events) != 1:
        crossing_reason = "no_unique_linear_zero_crossing"
    crossing, slope, event_indices = events[0] if len(events) == 1 else (None, None, None)
    peak0, reason0 = unique_peak(rx0)
    peak1, reason1 = unique_peak(rx1)
    reason = crossing_reason or reason0 or reason1
    crossing_visible = (
        None if event_indices is None else all(visible[index] for index in event_indices)
    )
    peak0_visible = None if peak0 is None else visible[peak0]
    peak1_visible = None if peak1 is None else visible[peak1]
    if reason is None and not crossing_visible:
        reason = "crossing_bracket_not_visible"
    if reason is None and (not peak0_visible or not peak1_visible):
        reason = "scheduled_peak_not_visible"
    order = "unavailable"
    if reason is None:
        delta = times_s[peak1] - times_s[peak0]
        if delta == 0:
            reason = "simultaneous_scheduled_peaks"
        elif slope == 0 or delta * slope <= 0:
            reason = "peak_order_disagrees_with_crossing_slope"
        else:
            order = "rx0_before_rx1" if delta > 0 else "rx1_before_rx0"
    return {
        "order": order,
        "reason": reason,
        "crossing_count": len(events),
        "crossing_time_utc_ns": (
            None if crossing is None else float(times_ns[0] + crossing * 1e9)
        ),
        "crossing_slope_per_s": slope,
        "crossing_event_visible": crossing_visible,
        "rx0_peak_visible": peak0_visible,
        "rx1_peak_visible": peak1_visible,
    }


def audit_panel(panel, dataset_path, result_path):
    document = json.loads(dataset_path.read_text())
    result = json.loads(result_path.read_text())
    if result.get("schema") != "rx-direction-support/v1" or result.get("status") != "complete":
        raise ValueError(f"{panel}: invalid result schema or status")
    if result.get("source_sha256", {}).get("dataset") != digest(dataset_path):
        raise ValueError(f"{panel}: result is not bound to dataset bytes")
    sources = {lane_key(lane["lane"]): lane for lane in document["lanes"]}
    outputs = {lane_key(lane["lane"]): lane for lane in result["lanes"]}
    if len(sources) != len(document["lanes"]) or set(sources) != set(outputs):
        raise ValueError(f"{panel}: lane membership mismatch")

    nominee_count = 0
    unavailable_with_nonzero_secant = 0
    available_orders = {"rx0_before_rx1": 0, "rx1_before_rx0": 0}
    reconstructed_crossing_counts = {"zero": 0, "one": 0, "multiple": 0}
    unavailable_reasons = {}
    for key, source in sources.items():
        output = outputs[key]
        components = source["components"][:-1]
        component_keys = [
            (component["track_id"], int(component["catalog_number"]))
            for component in components
        ]
        nominee_keys = [
            (nominee["track_id"], int(nominee["catalog_number"]))
            for nominee in output["nominees"]
        ]
        if nominee_keys != component_keys:
            raise ValueError(f"{panel}: nominee population/order mismatch")
        priors = normalized_priors(components)
        if not close(math.fsum(priors), 1.0):
            raise ValueError(f"{panel}: independently normalized priors do not sum to one")
        windows = sorted(source["windows"], key=lambda row: row["prediction_utc_ns"])
        times = [int(window["prediction_utc_ns"]) for window in windows]
        masses = {name: 0.0 for name in ("rx0_before_rx1", "rx1_before_rx0", "unavailable")}
        entropy = 0.0
        for index, (component, nominee, prior) in enumerate(
            zip(components, output["nominees"], priors, strict=True)
        ):
            if not close(nominee["prior"], prior):
                raise ValueError(f"{panel}: nominee prior mismatch")
            if component.get("log_prior") is None and (
                nominee["log_prior"] is not None or nominee["normalized_log_prior"] is not None
            ):
                raise ValueError(f"{panel}: zero-mass prior serialization mismatch")
            if prior > 0:
                entropy -= prior * math.log(prior)
            east, up, visible = [], [], []
            component_key = component_keys[index]
            for window in windows:
                matches = [
                    prediction
                    for prediction in window["predictions"]
                    if (
                        prediction["track_id"],
                        int(prediction["catalog_number"]),
                    )
                    == component_key
                ]
                if len(matches) != 1:
                    raise ValueError(f"{panel}: input prediction membership is not unique")
                east.append(float(matches[0]["los_enu_unit"]["east"]))
                up.append(float(matches[0]["los_enu_unit"]["up"]))
                visible.append(bool(matches[0]["visible"]))
            q = [2.0 * SIN10 * value for value in east]
            rx0 = [-SIN10 * e + COS10 * u for e, u in zip(east, up, strict=True)]
            rx1 = [SIN10 * e + COS10 * u for e, u in zip(east, up, strict=True)]
            support = independent_support(times, q, rx0, rx1, visible)
            crossing_bucket = (
                "zero"
                if support["crossing_count"] == 0
                else "one"
                if support["crossing_count"] == 1
                else "multiple"
            )
            reconstructed_crossing_counts[crossing_bucket] += 1
            if nominee["order"] != support["order"] or nominee["unavailable_reason"] != support[
                "reason"
            ]:
                raise ValueError(f"{panel}: independently derived order/censor mismatch")
            for name in ("crossing_event_visible", "rx0_peak_visible", "rx1_peak_visible"):
                if nominee[name] is not support[name]:
                    raise ValueError(f"{panel}: independently derived visibility mismatch")
            if support["crossing_time_utc_ns"] is None:
                if nominee["crossing_time_utc_ns"] is not None:
                    raise ValueError(f"{panel}: unexpected exported crossing time")
            elif abs(
                nominee["crossing_time_utc_ns"] - support["crossing_time_utc_ns"]
            ) > 512.0:
                raise ValueError(f"{panel}: reconstructed crossing differs by more than 512 ns")
            if support["crossing_slope_per_s"] is None:
                if nominee["crossing_slope_per_s"] is not None:
                    raise ValueError(f"{panel}: unexpected exported crossing slope")
            elif not close(
                nominee["crossing_slope_per_s"], support["crossing_slope_per_s"]
            ):
                raise ValueError(f"{panel}: independently reconstructed crossing slope mismatch")
            checks = {
                "q_min": min(q),
                "q_max": max(q),
                "q_first": q[0],
                "q_last": q[-1],
                "q_overall_secant_per_s": (q[-1] - q[0]) / ((times[-1] - times[0]) / 1e9),
                "visible_fraction": math.fsum(visible) / len(visible),
            }
            if any(not close(nominee[name], expected) for name, expected in checks.items()):
                raise ValueError(f"{panel}: geometry summary mismatch")
            if nominee["scheduled_points"] != len(windows) or nominee[
                "visible_scheduled_points"
            ] != sum(visible):
                raise ValueError(f"{panel}: scheduled support count mismatch")
            for receiver, values in (("rx0", rx0), ("rx1", rx1)):
                maximum = max(values)
                peak_indices = [i for i, value in enumerate(values) if value == maximum]
                interior = len(peak_indices) == 1 and peak_indices[0] not in (0, len(values) - 1)
                expected_peak = times[peak_indices[0]] if interior else None
                if nominee[f"{receiver}_peak_time_utc_ns"] != expected_peak:
                    raise ValueError(f"{panel}: scheduled peak reconstruction mismatch")
                expected_visible = visible[peak_indices[0]] if interior else None
                if nominee[f"{receiver}_peak_visible"] is not expected_visible:
                    raise ValueError(f"{panel}: scheduled peak visibility mismatch")
            order = nominee["order"]
            if order not in masses:
                raise ValueError(f"{panel}: invalid nominal order label")
            masses[order] += prior
            if order == "unavailable":
                if nominee["unavailable_reason"] is None:
                    raise ValueError(f"{panel}: unavailable order lacks censoring reason")
                unavailable_reasons[nominee["unavailable_reason"]] = (
                    unavailable_reasons.get(nominee["unavailable_reason"], 0) + 1
                )
                if abs(nominee["q_overall_secant_per_s"]) > 0:
                    unavailable_with_nonzero_secant += 1
            else:
                available_orders[order] += 1
                if nominee["unavailable_reason"] is not None:
                    raise ValueError(f"{panel}: available order has censoring reason")
                delta = nominee["rx1_peak_time_utc_ns"] - nominee["rx0_peak_time_utc_ns"]
                if delta * nominee["crossing_slope_per_s"] <= 0:
                    raise ValueError(f"{panel}: peak order and crossing slope disagree")
                expected_order = "rx0_before_rx1" if delta > 0 else "rx1_before_rx0"
                if order != expected_order:
                    raise ValueError(f"{panel}: nominal peak order label mismatch")
        nominee_count += len(components)
        if not close(math.fsum(masses.values()), 1.0):
            raise ValueError(f"{panel}: reconstructed order masses do not sum to one")
        if any(not close(output["order_mass"][name], value) for name, value in masses.items()):
            raise ValueError(f"{panel}: prior-weighted order mass mismatch")
        disagreement = 2.0 * masses["rx0_before_rx1"] * masses["rx1_before_rx0"]
        if not close(output["pair_disagreement_mass"], disagreement):
            raise ValueError(f"{panel}: opposite-order pair mass mismatch")
        if not close(output["prior_entropy_nats"], entropy) or not close(
            output["prior_effective_count"], math.exp(entropy)
        ):
            raise ValueError(f"{panel}: prior entropy/effective-count mismatch")
    if result["accounting"]["lanes"] != len(sources) or result["accounting"][
        "nominees"
    ] != nominee_count:
        raise ValueError(f"{panel}: top-level accounting mismatch")
    return {
        "dataset_sha256": digest(dataset_path),
        "result_sha256": digest(result_path),
        "lanes": len(sources),
        "nominees": nominee_count,
        "available_order_counts": available_orders,
        "independently_reconstructed_crossing_event_counts": reconstructed_crossing_counts,
        "independently_reconstructed_unavailable_reasons": unavailable_reasons,
        "unavailable_with_nonzero_endpoint_secant": unavailable_with_nonzero_secant,
        "endpoint_secant_interpretation": (
            "A nonzero endpoint q secant remains descriptive when the full peak/crossing order is "
            "censored; it was not promoted to an available order."
        ),
    }


def audit_partial_summary(direction_results):
    path = HERE / "direction-summary.json"
    summary = json.loads(path.read_text())
    panels = {}
    for panel, result_path in direction_results.items():
        result = json.loads(result_path.read_text())
        section = summary.get(panel, {})
        if section.get("source_sha256") != digest(result_path):
            raise ValueError(f"{panel}: partial summary source binding mismatch")
        expected = {lane_key(row["lane"]): row for row in result["lanes"]}
        actual = {lane_key(row["lane"]): row for row in section.get("lanes", [])}
        if set(expected) != set(actual):
            raise ValueError(f"{panel}: partial summary lane population mismatch")
        maximum = 0.0
        maximum_lane = None
        for key, lane in expected.items():
            positive = math.fsum(
                nominee["prior"]
                for nominee in lane["nominees"]
                if nominee["q_overall_secant_per_s"] > 0
            )
            negative = math.fsum(
                nominee["prior"]
                for nominee in lane["nominees"]
                if nominee["q_overall_secant_per_s"] < 0
            )
            row = actual[key]
            checks = {
                "full_order_disagreement_mass": lane["pair_disagreement_mass"],
                "partial_positive_secant_mass": positive,
                "partial_negative_secant_mass": negative,
                "partial_secant_disagreement_mass": 2.0 * positive * negative,
            }
            if any(not close(row[name], value) for name, value in checks.items()):
                raise ValueError(f"{panel}: partial secant summary mismatch")
            if checks["partial_secant_disagreement_mass"] > maximum:
                maximum = checks["partial_secant_disagreement_mass"]
                maximum_lane = lane["lane"]
        panels[panel] = {
            "source_sha256": digest(result_path),
            "lanes": len(expected),
            "maximum_partial_secant_disagreement_mass": maximum,
            "maximum_lane": maximum_lane,
        }
    return {
        "summary_sha256": digest(path),
        "panels": panels,
        "interpretation": (
            "Endpoint-secants describe the sampled partial arc only. Agreement, disagreement, or "
            "absence of opposite secants neither establishes nor rules out full crossing-order "
            "support beyond the scheduled geometry."
        ),
    }


def main():
    source = ROOT / "tools/rx_direction_support.py"
    tree = ast.parse(source.read_text())
    forbidden = {
        "observed",
        "canonical_rx0_hz",
        "candidate_id",
        "candidate_rank",
        "fractional_margin",
    }
    accessed = {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and node.value in forbidden
    }
    if accessed:
        raise ValueError(f"direction-support source references outcome fields: {sorted(accessed)}")
    panel_paths = {
        "pilot": (
            ROOT / "reports/2026_09_28_rx_geometry_association/dataset.json",
            HERE / "direction-pilot.json",
        ),
        "ds8": (
            ROOT / "reports/2026_09_28_rx_ds8_confirmation/dataset.json",
            HERE / "direction-ds8.json",
        ),
    }
    direction_results = {name: paths[1] for name, paths in panel_paths.items()}
    result = {
        "schema": "rx-direction-support-independent-audit/v1",
        "status": "passed",
        "source_sha256": digest(source),
        "forbidden_outcome_field_references": sorted(accessed),
        "panels": {
            name: audit_panel(name, dataset, output)
            for name, (dataset, output) in panel_paths.items()
        },
        "partial_secant_summary_audit": audit_partial_summary(direction_results),
    }
    destination = HERE / "audit_direction_final.json"
    with destination.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
