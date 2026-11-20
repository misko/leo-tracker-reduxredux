"""Extract comparison endpoints emitted by each prototype during its own run."""

ARMS = ("c0", "fitted_c")


def endpoints(method, report, row):
    case = row["case"]
    checks = report["checks"]
    if method == "01_stream":
        prefixes = checks["causal_prefix"][case]["prefixes"]
        return {f"at_{int(p['air_deadline_s'])}s": p["arms"] for p in prefixes}
    if method == "02_pilots":
        return {"all_blind": row["blind_control"]["arms"]}
    if method == "03_consensus":
        return {"unbalanced_compact": row["checks"]["compact_same_tracks"]}
    if method == "04_compact":
        return {"float64": row["float64_control"]["arms"]}
    if method == "05_stationary":
        return {"latest_anchor": {
            arm: row["arms"][arm]["last_anchor_control"] for arm in ARMS}}
    if method == "06_coreset":
        policies = checks["case_checks"][case]["comparison"]
        return {policy: policies[policy]["arms"] for policy in ("longest12", "full")}
    if method == "07_differences":
        return {"plus_wrapped_means": checks[case]["paired_changes_plus_wrapped_means_control"]["arms"]}
    if method == "08_grid":
        fit = checks["case_checks"][case]
        return {"49_cells": {arm: fit[arm]["coarse_only"] for arm in ARMS}}
    if method == "10_network":
        return {"shape_grid_peak": {
            arm: {"latlon": row["grid_peak_latlon"]} for arm in ARMS}}
    return {}


def compare_endpoints(method, report, reference, distance):
    for row in report["cases"]:
        for control, arms in endpoints(method, report, row).items():
            for arm in ARMS:
                primary_position = row["arms"][arm].get("latlon")
                control_position = arms[arm].get("latlon")
                primary_error = distance(primary_position, reference) if primary_position else None
                control_error = distance(control_position, reference) if control_position else None
                delta = None
                if primary_error is not None and control_error is not None:
                    delta = primary_error - control_error
                yield dict(method=method, control=control, case=row["case"], arm=arm,
                           primary_error_km=primary_error, control_error_km=control_error,
                           primary_minus_control_km=delta)
