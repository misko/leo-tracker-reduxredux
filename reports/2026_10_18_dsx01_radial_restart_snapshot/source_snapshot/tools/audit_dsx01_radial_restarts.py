"""Read-only consistency checks for the independent-start DSX01 campaign.

This reporter is not imported by inference and does not select scientific
results. Basin maps count starts and endpoints; they are not probabilities.
"""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from associate_merged_track_catalogue import write
from dsx01_inference_audit import element_epoch_ns

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports/2026_10_18_dsx01_radial_restarts"


def canonical_starts():
    points = [
        [float(e), float(n)] for e in range(-10, 11, 5) for n in range(-10, 11, 5)
        if e * e + n * n <= 100
    ]
    return sorted(points, key=lambda x: (float(np.linalg.norm(x)), x[0], x[1]))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message, errors):
    if not condition:
        errors.append(message)


def same_position(left, right):
    return np.array_equal(np.asarray(left)[:2], np.asarray(right)[:2])


def common_arms(arms, errors, label):
    require(set(arms) == {"c0", "fitted_c"}, f"{label}: incomplete c pair", errors)
    if set(arms) != {"c0", "fitted_c"}:
        return
    left, right = arms["c0"], arms["fitted_c"]
    for key in ("aliases", "rows", "members", "labels", "assignment_labels"):
        if key in left or key in right:
            require(left.get(key) == right.get(key), f"{label}: unmatched {key}", errors)
    require(
        same_position(left["fit"]["history"][0]["parameters"],
                      right["fit"]["history"][0]["parameters"]),
        f"{label}: c arms have different starting positions", errors,
    )


def check_result(data, path, protocol, directory, errors):
    """Check one stored result without rerunning or mutating its pipeline."""
    label = str(path.relative_to(directory))
    method, case, start_id = data["method"], data["case"], data["start_id"]
    starts = canonical_starts()
    require(0 <= start_id < 13, f"{label}: unknown start ID", errors)
    if 0 <= start_id < 13:
        require(same_position(data["start_east_north_km"], starts[start_id]),
                f"{label}: wrong start coordinate", errors)
    require(data.get("status") == "complete", f"{label}: incomplete status", errors)
    require(data.get("source_fingerprint") == protocol["source_fingerprint"],
            f"{label}: source fingerprint mismatch", errors)
    require(data.get("GPS_or_following_TLE_used") is False,
            f"{label}: missing strict no-GPS/future declaration", errors)
    receipt = data["input_audit"]
    cutoff = receipt["cutoff_utc_ns"]
    for key in ("latest_max_collection_utc_ns", "latest_max_epoch_utc_ns"):
        require(receipt[key] <= cutoff, f"{label}: noncausal {key}", errors)
    require(cutoff <= receipt["origin_utc_ns"], f"{label}: cutoff after scan", errors)
    require(receipt.get("previous_element_byte_epochs_validated") is True,
            f"{label}: previous TLE bytes unaudited", errors)
    for name in data["actual_report_inputs_read"]:
        p = Path(name)
        require(p.name not in {"atlas.json", "atlas_progress.json", "endpoints.json",
                              "seed_bundle.json", "conditional_smooth_background.json"},
                f"{label}: inherited estimate read {name}", errors)
        require("following" not in name.lower() and "oracle_only" not in name.lower(),
                f"{label}: diagnostic input read {name}", errors)
        if str(directory) + "/" in name:
            allowed = {
                directory / case / "discovery" / f"start_{start_id:02d}" / "discovery.json",
                directory / case / "normal" / f"start_{start_id:02d}" / "result.json",
            }
            require(p in allowed,
                    f"{label}: cross-start or unexpected learned input {name}", errors)
    if method == "discover":
        provenance = data["discovery_provenance"]
        require(provenance.get("zero_initial_radio_phase_and_smooth") is True,
                f"{label}: discovery was not zero-initialized", errors)
        require(provenance.get("saved_atlas_labels_calibration_or_site_read") is False,
                f"{label}: discovery inherited learned state", errors)
        require(same_position(provenance["alias_anchor_east_north_km"],
                              data["start_east_north_km"]),
                f"{label}: aliases were anchored at another location", errors)
        return
    discovery = directory / case / "discovery" / f"start_{start_id:02d}" / "discovery.json"
    require(discovery.exists() and data.get("discovery_sha256") == digest(discovery),
            f"{label}: own-start discovery hash mismatch", errors)
    if method.startswith("linear_"):
        parent = directory / case / "normal" / f"start_{start_id:02d}" / "result.json"
        require(parent.exists() and data.get("parent_sha256") == digest(parent),
                f"{label}: own-start normal parent hash mismatch", errors)
    common_arms(data["arms"], errors, label)
    for arm, value in data["arms"].items():
        require(same_position(value["fit"]["parameters"], value["endpoint_east_north_km"]),
                f"{label}/{arm}: endpoint differs from fitted parameters", errors)
        rows = value.get("association_metrics", {}).get("tracks", value.get("track_associations"))
        if rows is not None:
            points = sum(row["points"] for row in rows if row["compatible"])
            tracks = sum(bool(row["compatible"]) for row in rows)
            require(value["associated_points"] == points,
                    f"{label}/{arm}: incorrect associated-point count", errors)
            require(value["associated_tracks"] == tracks,
                    f"{label}/{arm}: incorrect associated-track count", errors)
    previous = data["start_east_north_km"]
    for number, record in enumerate(data.get("rounds", [])):
        arms = record.get("arms", record.get("fits"))
        common_arms(arms if "arms" in record else {
            arm: dict(fit=fit, aliases=fit["aliases"]) for arm, fit in arms.items()
        }, errors, f"{label}/round{number}")
        anchor = record.get("anchor", record.get("start_east_north_km"))
        require(same_position(anchor, previous), f"{label}/round{number}: wrong c0 anchor", errors)
        for arm, result in arms.items():
            fit = result.get("fit", result)
            require(same_position(fit["history"][0]["parameters"], anchor),
                    f"{label}/round{number}/{arm}: optimizer start differs from common anchor",
                    errors)
        final = arms["c0"].get("fit", arms["c0"])
        previous = final["parameters"][:2]


def check_history(case, errors):
    path = ROOT / "reports/2026_10_18_dsx01_clean_region" / case / "causal_history.json"
    data = json.loads(path.read_text())
    cutoff, count = data["cutoff_utc_ns"], 0
    for key in ("association_whitelist_used", "diagnostic_or_future_TLE_source_read",
                "earlier_scan_radio_or_position_used"):
        require(data.get(key) is False, f"{case}: unsafe causal-history declaration {key}", errors)
    for number, records in data["past_versions"].items():
        for record in records:
            epoch = element_epoch_ns(record["lines"])
            require(record["epoch"] <= cutoff and record["collected_utc_ns"] <= cutoff,
                    f"{case}/{number}: noncausal history metadata", errors)
            require(epoch <= cutoff and abs(epoch - record["epoch"]) <= 100000,
                    f"{case}/{number}: noncausal/mismatched history bytes", errors)
            count += 1
    return dict(case=case, records_checked=count, sha256=digest(path))


def audit(directory=OUTPUT):
    directory = Path(directory).resolve()
    protocol = json.loads((directory / "protocol.json").read_text())
    errors, records, stops = [], [], Counter()
    starts = canonical_starts()
    require(len(starts) == 13, "canonical restart disk must contain 13 starts", errors)
    basin_key = "plots_are_start_to_endpoint_basin_maps_not_pointwise_loss_surfaces"
    require(protocol.get(basin_key) is True,
            "protocol does not distinguish basin maps from loss surfaces", errors)
    for declared in protocol["starts"]:
        require(same_position(declared["east_north_km"], starts[declared["start_id"]]),
                "protocol start coordinate does not match its canonical index", errors)
    for relative, expected in protocol.get("source_bindings", {}).items():
        path = ROOT / relative
        require(path.exists() and digest(path) == expected, f"source changed: {relative}", errors)
    expected = [
        (case, method, start["start_id"])
        for case in protocol["cases"] for method in ["discover", *protocol["methods"]]
        for start in protocol["starts"]
    ]
    missing, budget_locations = [], []
    for case, method, start in expected:
        folder, basename = ("discovery", "discovery.json") if method == "discover" else (
            method, "result.json"
        )
        path = directory / case / folder / f"start_{start:02d}" / basename
        if not path.exists():
            missing.append(dict(case=case, method=method, start_id=start))
            continue
        data = json.loads(path.read_text())
        before = len(errors)
        check_result(data, path, protocol, directory, errors)
        for arm, value in data.get("arms", {}).items():
            fit = value["fit"]
            stopped = fit.get(
                "stopped", "scalar_converged" if fit.get("converged") else "scalar_unconverged"
            )
            stops[stopped] += 1
            if stopped == "iteration_budget":
                budget_locations.append(dict(
                    case=case, method=method, start_id=start, arm=arm, score=fit["score"]
                ))
        records.append(dict(case=case, method=method, start_id=start, passed=len(errors) == before))
    histories = [check_history(case, errors) for case in protocol["cases"]]
    return dict(
        passed=not errors,
        complete=not missing,
        expected_artifacts=len(expected),
        available_artifacts=len(records),
        expected_paired_pipeline_runs=(
            len(expected) - len(protocol["cases"]) * len(protocol["starts"])
        ),
        full_campaign_paired_pipeline_runs=5 * 49 * 13,
        declared_start_count=len(protocol["starts"]),
        canonical_disk_start_count=13,
        errors=errors,
        missing=missing,
        endpoint_stop_distribution=dict(stops),
        iteration_budget_endpoints=stops["iteration_budget"],
        iteration_budget_locations=budget_locations,
        histories=histories,
        records=records,
        interpretation=(
            "Start-to-endpoint convergence samples, "
            "not calibrated probabilities or exhaustive basins"
        ),
        limitation=(
            "Stored receipts and outputs checked; no cold pipeline replay or global optimum proof"
        ),
    )


def replay_endpoint_gradients(directory=OUTPUT):
    """Replay four existing S01 objectives and measure local 50-m gradients.

    This never optimizes, renominates, selects or changes a saved result.
    A no-accepted-step optimizer status is not proof of a stationary point.
    """
    from map_dsx01_clean_region import factory, finite_gradient, loss
    from run_dsx01_clean_region import load_scan

    directory = Path(directory)
    scan, sigma = load_scan("DSX01-S01")
    rows = []
    for start_id in (0, 12):
        path = directory / "DSX01-S01/normal" / f"start_{start_id:02d}" / "result.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        for arm, stored in data["arms"].items():
            p = factory(
                scan, data["final_node"], sigma, "normal", arm == "fitted_c",
                reference=data["final_reference"],
            )
            x = np.asarray(stored["fit"]["parameters"], float)
            score = loss(p, x)
            gradient = finite_gradient(lambda point, p=p: loss(p, point), x, step=0.05)
            rows.append(dict(
                case="DSX01-S01", method="normal", start_id=start_id, arm=arm,
                result_sha256=digest(path), source_fingerprint=data["source_fingerprint"],
                endpoint_east_north_km=x,
                stored_score=stored["fit"]["score"], replay_score=score,
                score_difference=score - stored["fit"]["score"],
                gradient_loss_per_km=gradient,
                gradient_magnitude_loss_per_km=float(np.linalg.norm(gradient)),
                optimizer_stop=stored["fit"].get("stopped"),
                derivative_step_km=0.05,
            ))
    return dict(
        passed=bool(rows) and all(abs(row["score_difference"]) < 1e-7 for row in rows),
        expected_replays=4, available_replays=len(rows),
        complete=len(rows) == 4,
        max_absolute_score_difference=max(
            (abs(row["score_difference"]) for row in rows), default=None
        ),
        rows=rows,
        inference_or_optimization_rerun=False,
        interpretation=(
            "Conditional endpoint objective replay and local derivative, not a global basin test"
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=OUTPUT)
    parser.add_argument("--replay-endpoint-gradients", action="store_true")
    args = parser.parse_args()
    result = audit(args.directory)
    if args.replay_endpoint_gradients:
        replay = replay_endpoint_gradients(args.directory)
        write(args.directory / "endpoint_gradient_replay.json", replay)
        result["endpoint_replay_passed"] = replay["passed"]
        result["passed"] &= replay["passed"]
    write(args.directory / "consistency_audit.json", result)
    print(json.dumps({k: v for k, v in result.items() if k not in ("records", "missing")}))
    if not result["passed"]:
        raise SystemExit("restart consistency audit failed")
