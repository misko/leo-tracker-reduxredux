"""Independent, report-only DS23 combined-recovery evaluation.

Association numerators are unique original GLRT observation IDs. Geographic
truth enters only this evaluator, after the inference results are sealed.
"""

from __future__ import annotations

import argparse
from collections import Counter
from concurrent.futures import ProcessPoolExecutor, as_completed
import csv
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from report_algo02_ds23 import position_error, summarize
from run_algo01_ds23_sample import ROOT, read, sha, write

OUT = ROOT / "reports/2026_10_20_ds23_combined_recovery_full"
ORIGINAL = ROOT / "reports/2026_10_19_algo02_ds23_full"
SIGNED_AUDIT = ROOT / "reports/2026_10_20_ds23_signed_recoveries/evaluation_audit.json"
ARMS = ("c0", "fitted_c")
METHODS = ("original_ALGO02", "signed_prior", "combined_recovery")
COLORS = {"original_ALGO02": "#7a818a", "signed_prior": "#197c91",
          "combined_recovery": "#c44c31"}


def verify_scientific_inputs(root, case):
    """Replay the original preparation's complete scientific input hash receipt."""
    receipt_path = ORIGINAL / case / "preparation_receipt.json"
    receipt = read(receipt_path)
    if not receipt["no_GPS_or_previous_results"] or not receipt["all_TLEs_causal"]:
        raise ValueError("original input preparation lacks causal GPS-free provenance")
    expected = receipt["files_sha256"]
    required = {f"{case}/{name}" for name in (
        "tracking.json", "tracks.json", "observations.json", "bank.npz", "radio_noise.json",
        "receipt.json", "nominal_elements.json")}
    required |= {f"causal_prior/{case}/{name}" for name in
                 ("previous.tle", "previous_receipt.json", "receipt.json")}
    required |= {f"causal_phase_history/{case}{suffix}.json" for suffix in ("", "_forecast")}
    if not required <= set(expected):
        raise ValueError("original preparation receipt lacks scientific input bindings")
    actual = {}
    for relative, digest in expected.items():
        original_path, selected_path = ORIGINAL / relative, root / relative
        if sha(original_path) != digest:
            raise ValueError("original scientific input changed: " + relative)
        if selected_path.exists():
            if sha(selected_path) != digest:
                raise ValueError("combined scientific input changed: " + relative)
            actual[relative] = digest
        elif relative in required:
            raise ValueError("combined scientific input is missing: " + relative)
    if sha(root / case / "tracking.json") != receipt["tracking_sha256"]:
        raise ValueError("original tracking contract differs from preparation receipt")
    return dict(preparation_receipt_sha256=sha(receipt_path),
                input_sha256=actual,
                input_bindings_sha256=hashlib.sha256(json.dumps(
                    actual, sort_keys=True, separators=(",", ":")).encode()).hexdigest())


def independent_counts(accepted_tracks, tracks, observations):
    """Reject duplicate owners and count winners separately from other peaks."""
    original_ids = [o["observation_id"] for o in observations]
    if len(original_ids) != len(set(original_ids)) or not original_ids:
        raise ValueError("original GLRT denominator must contain unique observations")
    originals = set(original_ids)
    by_key = {t["key"]: t for t in tracks}
    if len(by_key) != len(tracks):
        raise ValueError("graph track keys are not unique")
    owned, accepted, families = [], [], set()
    for row in accepted_tracks:
        if not row["compatible"]:
            continue
        component = row["component"]
        if component not in by_key:
            raise ValueError("accepted component is absent from the replayed graph")
        ids = row.get("observation_ids", by_key[component]["observation_ids"])
        if not set(ids) <= set(by_key[component]["observation_ids"]):
            raise ValueError("accepted observation is absent from its graph track")
        if row.get("points", len(ids)) != len(ids):
            raise ValueError("accepted point count disagrees with unique observation IDs")
        owned.extend(ids)
        accepted.append(component)
        family = row.get("norad", row.get("candidate_norad"))
        if family is None:
            raise ValueError("accepted track has no satellite family identity")
        families.add(int(family))
    if len(accepted) != len(set(accepted)) or len(owned) != len(set(owned)):
        raise ValueError("a physical measurement has multiple accepted owners")
    ids = set(owned)
    return dict(original_GLRT_points=len(originals),
                associated_original_points=len(ids & originals),
                associated_original_percent=100 * len(ids & originals) / len(originals),
                associated_additional_peaks=len(ids - originals),
                associated_points=len(ids), associated_tracks=len(accepted),
                associated_families=len(families),
                associated_original_observation_ids=sorted(ids & originals))


def compare_memberships(original, combined):
    old = set(original["associated_original_observation_ids"])
    new = set(combined["associated_original_observation_ids"])
    return dict(newly_associated_original_points=len(new - old),
                no_longer_associated_original_points=len(old - new),
                retained_original_points=len(new & old),
                net_associated_original_points=len(new) - len(old))


def check_endpoint_replay(saved, fresh, case, arm):
    score = float(fresh["negative_twice_elbo"] - saved["negative_twice_elbo"])
    tolerance = max(1e-3, 1e-8 * abs(saved["negative_twice_elbo"]))
    if not np.isfinite(score) or abs(score) > tolerance:
        raise ValueError(f"{case} {arm}: RF objective failed independent replay ({score})")
    if fresh["linear_calibration_max_difference"] > 1e-10:
        raise ValueError(f"{case} {arm}: predictive observations changed calibration")
    np.testing.assert_allclose(fresh["endpoint_latlon"], saved["endpoint_latlon"],
                               rtol=0, atol=1e-10)
    left = {(r["component"], bool(r["compatible"])) for r in saved["gates"]["tracks"]}
    right = {(r["component"], bool(r["compatible"])) for r in fresh["gates"]["tracks"]}
    if left != right:
        raise ValueError(f"{case} {arm}: original acceptance gate replay changed")
    if len(left) != len(saved["gates"]["tracks"]) or len(right) != len(fresh["gates"]["tracks"]):
        raise ValueError(f"{case} {arm}: duplicate calibration track owners")
    # Early curved-only ALGO02 records predate the optional predictive gate key.
    saved_linear_rows = saved.get("linear_gates", [])
    saved_linear = {(r["component"], bool(r["compatible"])) for r in saved_linear_rows}
    fresh_linear = {(r["component"], bool(r["compatible"])) for r in fresh["linear_gates"]}
    if saved_linear != fresh_linear:
        raise ValueError(f"{case} {arm}: predictive acceptance gate replay changed")
    if len(saved_linear) != len(saved_linear_rows) or len(fresh_linear) != len(fresh["linear_gates"]):
        raise ValueError(f"{case} {arm}: duplicate predictive track owners")
    return score


def replay_endpoint(p, entries, saved, observations, case, arm):
    """Recompute objective, original gates and full-graph associations from RF."""
    from ds23_frequency_events import extend_event_associations
    from probe_ds23_frequency_events import cached, summary

    cached(p)
    x = np.asarray(saved["endpoint_east_north_km"])
    fresh = summary(p, x, entries)
    fresh["final_phase_change_s"] = saved.get("final_phase_change_s", 0.)
    difference = check_endpoint_replay(saved, fresh, case, arm)
    extension = extend_event_associations(p, x, fresh["gates"])
    accepted = {r["component"]: r for r in extension["tracks"] if r["compatible"]}
    # The actual retained subsets override whole-curve extension proposals.
    for row in fresh["gates"]["tracks"] + fresh["linear_gates"]:
        if row["compatible"]:
            accepted[row["component"]] = row
    counts = independent_counts(list(accepted.values()), p.scan.tracks, observations)
    if counts["associated_additional_peaks"]:
        raise ValueError("additional peaks entered the fixed original GLRT population")
    position_ids = [oid for i, sl in zip(p.members, p.slices, strict=True)
                    for oid, keep in zip(p.scan.tracks[i]["observation_ids"], p.keep[sl], strict=True)
                    if keep]
    position_ids += [oid for entry in entries for oid in entry["observation_ids"]]
    if len(position_ids) != len(set(position_ids)):
        raise ValueError("a physical observation appears twice in the position objective")
    position_digest = hashlib.sha256(json.dumps(sorted(position_ids), separators=(",", ":")).encode()).hexdigest()
    return dict(**counts, endpoint_latlon=fresh["endpoint_latlon"],
                position_observation_ids_sha256=position_digest,
                position_observation_ids=position_ids,
                position_error_km_report_only=position_error(fresh["endpoint_latlon"]),
                frequency_RMS_hz=fresh["RMS_hz"],
                negative_twice_elbo=fresh["negative_twice_elbo"],
                curved_negative_twice_elbo=fresh["curved_negative_twice_elbo"],
                objective_replay_difference=difference,
                position_curved_points=fresh["active_points"],
                position_predictive_points=fresh["predictive_points"],
                associated_track_rows=list(accepted.values())), fresh


def summarize_rows(rows, population):
    """Keep scan and measurement denominators distinct, including missing scans."""
    result = {}
    for method in METHODS:
        result[method] = {}
        for arm in ARMS:
            available = [r for r in rows if r["method"] == method and r["arm"] == arm
                         and r["status"] == "accepted"]
            errors = [r["position_error_km_report_only"] for r in available]
            numerator = sum(r["associated_original_points"] for r in available)
            denominator = sum(r["original_GLRT_points"] for r in available)
            result[method][arm] = dict(
                position=summarize(errors, population),
                association=dict(available_scans=len(available),
                    available_original_GLRT_points=denominator,
                    associated_original_points=numerator,
                    point_weighted_original_association_percent=(
                        100 * numerator / denominator if denominator else None),
                    mean_scan_association_percent=(float(np.mean([
                        r["associated_original_percent"] for r in available])) if available else None),
                    total_associated_tracks=sum(r["associated_tracks"] for r in available),
                    sum_scan_family_counts=sum(r["associated_families"] for r in available)))
    return result


def paired_changes(rows):
    by_key = {(r["case"], r["method"], r["arm"]): r for r in rows
              if r["status"] == "accepted"}
    changes = []
    for (case, method, arm), row in sorted(by_key.items()):
        if method != "combined_recovery":
            continue
        for control in ("original_ALGO02", "signed_prior"):
            before = by_key[(case, control, arm)]
            delta = row["position_error_km_report_only"] - before["position_error_km_report_only"]
            changes.append(dict(case=case, arm=arm, control=control,
                error_change_km=delta,
                association_change_percentage_points=(row["associated_original_percent"]
                                                       - before["associated_original_percent"]),
                frequency_RMS_change_hz=row["frequency_RMS_hz"] - before["frequency_RMS_hz"],
                negative_twice_elbo_change=row["negative_twice_elbo"] - before["negative_twice_elbo"],
                objective_comparison_uses_different_observation_sets=(
                    row["position_observation_ids_sha256"] != before["position_observation_ids_sha256"]),
                **(row["membership_changes"][control] if "membership_changes" in row
                   else compare_memberships(before, row))))
    return changes


def paired_comparison_statistics(changes):
    result = {}
    for control in ("original_ALGO02", "signed_prior"):
        result[control] = {}
        for arm in ARMS:
            group = [r for r in changes if r["control"] == control and r["arm"] == arm]
            if not group:
                result[control][arm] = dict(count=0)
                continue
            error = np.asarray([r["error_change_km"] for r in group])
            association = np.asarray([r["association_change_percentage_points"] for r in group])
            result[control][arm] = dict(count=len(group),
                mean_error_change_km=float(error.mean()), median_error_change_km=float(np.median(error)),
                improved_scans=int(sum(error < -1e-8)), worsened_scans=int(sum(error > 1e-8)),
                unchanged_scans=int(sum(abs(error) <= 1e-8)),
                maximum_error_increase_km=float(error.max()),
                maximum_error_decrease_km=float(error.min()),
                mean_association_change_percentage_points=float(association.mean()),
                newly_associated_original_points=sum(r["newly_associated_original_points"] for r in group),
                no_longer_associated_original_points=sum(r["no_longer_associated_original_points"] for r in group))
    return result


def calibration_ablation(rows):
    by_key = {(r["case"], r["method"], r["arm"]): r for r in rows if r["status"] == "accepted"}
    result = {}
    for method in METHODS:
        pairs = [(r, by_key[(case, method, "fitted_c")])
                 for (case, current, arm), r in by_key.items()
                 if current == method and arm == "c0"]
        if not pairs:
            result[method] = dict(count=0)
            continue
        result[method] = dict(count=len(pairs),
            position_accuracy=dict(mean_fitted_minus_c0_error_km=float(np.mean([
                fitted["position_error_km_report_only"] - fixed["position_error_km_report_only"]
                for fixed, fitted in pairs]))),
            frequency_fit=dict(mean_fitted_minus_c0_RMS_hz=float(np.mean([
                fitted["frequency_RMS_hz"] - fixed["frequency_RMS_hz"] for fixed, fitted in pairs])),
                mean_fitted_minus_c0_negative_twice_elbo=float(np.mean([
                    fitted["negative_twice_elbo"] - fixed["negative_twice_elbo"] for fixed, fitted in pairs]))))
    return result


def measured_runtime(row):
    """Interrupted checkpoint times cannot stand in for measured elapsed time."""
    return (row.get("seconds") is not None and row["seconds"] > 0
            and not row.get("seconds_is_checkpoint_lower_bound", False))


def _original_problem(scan, node, old, arm, saved, means):
    from ds23_frequency_events import attach_event_predictive, make_event_problem

    entries = old["linear_entries"] if old["linear_paired_valid"] else []
    p = make_event_problem(scan, node, np.asarray(old["mask"], bool), arm,
                           np.asarray(saved["phase_reference"]), np.asarray(old["weights"]),
                           means, old["hyperparameters_from_pre_RF_TLE_only"], [])
    attach_event_predictive(p, entries, np.asarray(old["weights"]))
    return p, entries


def evaluate_case(case, directory):
    """An isolated process replays all three methods for a single scan."""
    from algo02_scan import pair_passes, validate_history
    from ds23_causal_phase_location import adjust_means, qualify
    from investigate_ds23_adaptive_failures import phase_widths
    from probe_ds23_causal_phase_mean import forecast_phase_mean
    import run_ds23_combined_recovery_full as runner

    directory = Path(directory)
    runner.OUT = directory
    context, reconstruct = runner.context, runner.reconstruct
    path = directory / case / "result.json"
    record = read(path)
    protocol = read(directory / "protocol.json")
    if record["source_protocol_sha256"] != sha(directory / "protocol.json"):
        raise ValueError("combined record belongs to another frozen inference protocol")
    audit = read(SIGNED_AUDIT)
    binding = audit["evidence"][case]
    signed_path = ROOT / binding["path"]
    if sha(signed_path) != binding["sha256"]:
        raise ValueError("signed control changed after its independent evidence audit")
    signed = read(signed_path)
    root = Path(record["input_root"])
    if not root.is_absolute():
        root = ROOT / root
    if root.resolve() != Path(protocol["input_roots"][case]).resolve():
        raise ValueError("combined record changed the original input root")
    original_path = root / case / "algo02_result.json"
    if sha(original_path) != protocol["baseline_sha256"][case]:
        raise ValueError("original ALGO02 baseline changed after combined protocol freeze")
    if root.resolve() != ORIGINAL.resolve():
        copied = read(root / "protocol.json")["input_sha256"]
        copied = copied[case] if case in copied else copied
        for relative, expected in copied.items():
            if sha(root / relative) != expected or sha(ORIGINAL / relative) != expected:
                raise ValueError("original recovery copied input changed")
    scientific_inputs = verify_scientific_inputs(root, case)
    observations_path = root / case / "observations.json"
    history_path = root / "causal_phase_history" / (case + ".json")
    forecast_path = root / "causal_phase_history" / (case + "_forecast.json")
    bindings = dict(result_sha256=sha(path), original_sha256=sha(original_path),
                    signed_sha256=sha(signed_path), evaluator_sha256=sha(Path(__file__)),
                    observations_sha256=sha(observations_path), history_sha256=sha(history_path),
                    forecast_sha256=sha(forecast_path),
                    preparation_receipt_sha256=scientific_inputs["preparation_receipt_sha256"],
                    scientific_input_bindings_sha256=scientific_inputs["input_bindings_sha256"])
    cache = directory / "independent_replays" / (case + ".json")
    if cache.exists():
        previous = read(cache)
        if previous["bindings"] == bindings:
            return dict(case=case, cached=True, rows=len(previous["rows"]))
        before = {k: v for k, v in previous["bindings"].items() if k != "evaluator_sha256"}
        after = {k: v for k, v in bindings.items() if k != "evaluator_sha256"}
        if before != after:
            raise ValueError("a sealed independent replay input changed")
    started = time.monotonic()
    scan, node, mask, base, old = context(case)
    if old != read(original_path) or record["baseline_arms"] != old["policy_arms"]:
        raise ValueError("combined method changed the matched ordinary ALGO02 baseline")
    if signed["baseline_arms"] != old["policy_arms"]:
        raise ValueError("signed control does not share the original baseline")
    for candidate in (record, old, signed):
        if candidate.get("GPS_used") is not False or candidate.get("future_TLE_used") is not False:
            raise ValueError("inference result is not certified GPS-free and causal")
    np.testing.assert_array_equal(record["original_mask"], old["mask"])
    np.testing.assert_array_equal(mask, old["mask"])
    history, forecast = read(history_path), read(forecast_path)
    model, _ = validate_history(history, forecast, scan, sha(history_path))
    if model != old["hyperparameters_from_pre_RF_TLE_only"]:
        raise ValueError("ordinary ALGO02 causal prior changed")
    if old["history_sha256"] != sha(history_path) or old["history_forecast_sha256"] != sha(forecast_path):
        raise ValueError("ordinary ALGO02 causal history input changed")
    if signed["history_sha256"] != sha(history_path) or signed["forecast_sha256"] != sha(forecast_path):
        raise ValueError("signed control causal history input changed")
    if any(r["validation_time_ns"] > scan.receipt["cutoff_utc_ns"]
           for r in forecast["transitions"]):
        raise ValueError("signed qualification includes a post-scan TLE target")
    _, receipts = phase_widths(scan, base.labels)
    means = forecast_phase_mean(receipts, model["shrinkage"])
    np.testing.assert_allclose(signed["original_means_s"], means, rtol=0, atol=1e-12)
    selection = qualify(forecast["transitions"], forecast["temporal_split_boundary_ns"],
                        forecast["prefix_distribution"], model)
    if selection != signed["selection"]:
        raise ValueError("signed control historical qualification changed")
    signed_means = adjust_means(means, receipts, model, selection)
    np.testing.assert_allclose(signed["means_s"], signed_means, rtol=0, atol=1e-12)
    if not signed["accepted"]:
        signed_means = means
    observations = read(observations_path)
    member = next(r for r in read(ORIGINAL / "sample.json")["selected"]
                  if r["dataset_label"] == case)
    rows, replays = [], {}
    selected_signatures = []
    for method in METHODS:
        current = old if method == "original_ALGO02" else signed if method == "signed_prior" else record
        replays[method] = {}
        for arm in ARMS:
            saved = current["policy_arms"][arm]
            if method == "combined_recovery":
                p, x, entries = reconstruct(case, record, arm)
                np.testing.assert_allclose(x, saved["endpoint_east_north_km"], rtol=0, atol=0)
                policy_model = record["policy_model"]
                if policy_model["hyper"] != model:
                    raise ValueError("combined recovery replaced the ordinary ALGO02 prior")
                _, selected_receipts = phase_widths(p.scan, p.labels)
                ordinary_selected_means = forecast_phase_mean(selected_receipts, model["shrinkage"])
                np.testing.assert_allclose(np.asarray(policy_model["means"])[p.labels], ordinary_selected_means,
                                           rtol=0, atol=1e-12)
                selected_signatures.append(dict(rows=p.rows, aliases=np.asarray(p.alias).tolist(),
                    mask=np.asarray(p.keep).tolist(), entries=entries, labels=p.labels))
            else:
                local_means = signed_means if method == "signed_prior" else means
                p, entries = _original_problem(scan, node, old, arm, saved, local_means)
            metrics, fresh = replay_endpoint(p, entries, saved, observations, case, arm)
            replays[method][arm] = fresh
            rows.append(dict(case=case, method=method, arm=arm, status="accepted",
                recording_format=member["recording_format"],
                recovery_pipeline_status=record.get("status") if method == "combined_recovery" else None,
                recovery_pipeline_complete=(record.get("status") == "complete") if method == "combined_recovery" else None,
                recovery_terminal_error=record.get("error") if method == "combined_recovery" else None,
                selected_pair_independently_qualified=True,
                used_original_pair=(record["policy_arms"] == old["policy_arms"]) if method == "combined_recovery" else None,
                accepted_recovery_stages=(";".join(s["name"] for s in record["stages"] if s.get("accepted"))) if method == "combined_recovery" else None,
                seconds_is_checkpoint_lower_bound=current.get("seconds_is_checkpoint_lower_bound", False),
                charged_inference_budget_seconds=current.get("charged_inference_budget_seconds"),
                fallback=("original_ALGO02" if method == "combined_recovery" and
                          record["policy_arms"] == old["policy_arms"] else current.get("fallback")),
                paired_valid=current.get("paired_valid"),
                seconds=current.get("seconds"), **metrics))
        if not pair_passes(replays[method], include_linear=bool(entries)):
            raise ValueError(f"{case}: {method} selected policy fails paired acceptance replay")
    if selected_signatures[0] != selected_signatures[1]:
        raise ValueError("combined c arms do not share the same observation and candidate sets")
    for arm in ARMS:
        selected = {r["method"]: r for r in rows if r["arm"] == arm}
        combined = selected["combined_recovery"]
        if not set(selected["original_ALGO02"]["position_observation_ids"]) <= set(combined["position_observation_ids"]):
            raise ValueError("combined recovery removed original position observations")
        combined["membership_changes"] = {control: compare_memberships(selected[control], combined)
            for control in ("original_ALGO02", "signed_prior")}
        combined.update(combined["membership_changes"]["original_ALGO02"])
    # The graph and sealed model reproduce IDs; retain compact digests and counts.
    for row in rows:
        ids = row.pop("associated_original_observation_ids")
        row["associated_original_ids_sha256"] = hashlib.sha256(
            json.dumps(ids, separators=(",", ":")).encode()).hexdigest()
        row.pop("associated_track_rows")
        row.pop("position_observation_ids")
    cache.parent.mkdir(parents=True, exist_ok=True)
    write(cache, dict(case=case, bindings=bindings, rows=rows,
                     scientific_input_sha256=scientific_inputs["input_sha256"],
                     independent_replay_seconds=time.monotonic() - started,
                     paired_original_gates_replayed=True,
                     geographic_truth_used_only_for_reporting=True))
    return dict(case=case, cached=False, seconds=time.monotonic() - started)


def _verify_protocol(directory):
    from run_algo02_ds23 import verify_freeze

    verify_freeze(ORIGINAL)
    protocol = read(directory / "protocol.json")
    for relative, expected in protocol["source_sha256"].items():
        source = ROOT / relative if "/" in relative else ROOT / "tools" / relative
        if sha(source) != expected:
            raise ValueError("combined inference implementation changed after freeze: " + relative)
    sample = read(ORIGINAL / "sample.json")
    population = [r["dataset_label"] for r in sample["selected"]]
    if len(population) != 413 or len(set(population)) != 413:
        raise ValueError("original DS23 sample membership changed")
    if set(protocol["cases"]) != set(population):
        raise ValueError("combined evaluation changed the original DS23 population")
    available = set(protocol["available_cases"])
    missing = set(protocol["missing_cases"])
    if available & missing or available | missing != set(population):
        raise ValueError("available and missing scans do not partition the full population")
    if len(available) != 410 or len(missing) != 3:
        raise ValueError("unexpected original ALGO02 availability population")
    if available != set(read(SIGNED_AUDIT)["evidence"]):
        raise ValueError("controls do not share exactly the same available scans")
    return protocol, sample


def collect(directory, workers=30, allow_partial=False):
    directory = Path(directory)
    protocol, sample = _verify_protocol(directory)
    available = set(protocol["available_cases"])
    ready = sorted(case for case in available if (directory / case / "result.json").exists())
    pending = sorted(available - set(ready))
    if pending and not allow_partial:
        raise ValueError(f"{len(pending)} available scans have no combined result yet")
    errors, receipts = [], []
    started = time.monotonic()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(evaluate_case, case, str(directory)): case for case in ready}
        for future in as_completed(futures):
            case = futures[future]
            try:
                receipts.append(future.result())
            except Exception as exc:
                errors.append(dict(case=case, error=repr(exc)))
            if (len(receipts) + len(errors)) % 20 == 0 or len(receipts) + len(errors) == len(ready):
                print(f"independent replay {len(receipts) + len(errors)}/{len(ready)}; errors={len(errors)}", flush=True)
                write(directory / "independent_replay_execution.json", dict(receipts=receipts,
                    errors=errors, pending=pending, workers=workers,
                    seconds=time.monotonic() - started))
    if errors:
        raise RuntimeError("independent RF replay failed; see independent_replay_execution.json")
    rows, evidence = [], {}
    for case in ready:
        path = directory / "independent_replays" / (case + ".json")
        replay = read(path)
        rows.extend(replay["rows"])
        evidence[case] = dict(path=str(path.relative_to(ROOT)), sha256=sha(path))
    for member in sample["selected"]:
        case = member["dataset_label"]
        if case in ready:
            continue
        for method in METHODS:
            for arm in ARMS:
                rows.append(dict(case=case, method=method, arm=arm,
                    status="pending" if case in pending else "original_input_unavailable",
                    recording_format=member["recording_format"]))
    changes = paired_changes(rows)
    statistics = summarize_rows(rows, 413)
    subgroups = {}
    development = set(sample.get("development_cases", []))
    for name, predicate in (
        ("excluding_demonstration_scan_DS23_0268", lambda r: r["case"] != "DS23-0268"),
        ("outside_original_development", lambda r: r["case"] not in development),
        ("adaptive", lambda r: r["recording_format"] == "starlink_adaptive_hop_iq"),
        ("fast", lambda r: r["recording_format"] == "short_window_iq_recording")):
        selected = [r for r in rows if predicate(r)]
        subgroups[name] = summarize_rows(selected, len({r["case"] for r in selected}))
    slim_rows = [{k: v for k, v in r.items() if k not in
                 ("associated_track_rows", "associated_original_observation_ids")} for r in rows]
    fields = sorted({key for row in slim_rows for key in row})
    with (directory / "per_scan_evaluation.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader(); writer.writerows(slim_rows)
    write(directory / "evaluation_audit.json", dict(evidence=evidence,
        protocol_sha256=sha(directory / "protocol.json"),
        signed_control_audit_sha256=sha(SIGNED_AUDIT), evaluator_sha256=sha(Path(__file__)),
        independently_verified_scans=len(ready), full_population=413,
        all_available_scans_independently_replayed=not pending,
        paired_original_gates_replayed=True, no_GPS_inference_or_new_RF=True))
    result = dict(population=413, available=len(ready), missing_cases=protocol["missing_cases"],
        pending_cases=pending, complete=not pending, statistics=statistics, subgroups=subgroups,
        ledger_complete=not pending,
        full_algorithm_completed_all_available=(not pending and all(
            r.get("recovery_pipeline_status") == "complete" for r in rows
            if r["method"] == "combined_recovery" and r["status"] == "accepted")),
        paired_comparisons=paired_comparison_statistics(changes),
        excluding_demonstration_scan_paired_comparisons=paired_comparison_statistics([
            r for r in changes if r["case"] != "DS23-0268"]),
        matched_c0_fitted_c_ablation=calibration_ablation(rows),
        paired_changes=changes, all_rows=slim_rows,
        statuses=dict(Counter(r["status"] for r in rows if r["method"] == "combined_recovery" and r["arm"] == "c0")),
        recovery_pipeline_statuses=dict(Counter(r.get("recovery_pipeline_status") for r in rows
            if r["method"] == "combined_recovery" and r["arm"] == "c0")),
        geographic_truth_used_only_for_reporting=True,
        association_definition="Unique accepted original GLRT winner IDs / original scan winner IDs; no additional peaks.",
        frequency_fit_and_position_accuracy_reported_separately=True,
        changed_data_objectives_not_directly_comparable=True,
        runtime_definition="Archived per-method stage seconds; excludes input preparation and differs in baseline work; no speedup claim. Interrupted checkpoint times are lower bounds and excluded from measured-runtime comparisons.")
    result["runtime"] = {}
    for method in METHODS:
        group = [r for r in rows if r["status"] == "accepted" and r["method"] == method and r["arm"] == "c0"]
        seconds = np.asarray([r["seconds"] for r in group if measured_runtime(r)])
        result["runtime"][method] = dict(count=len(seconds),
            interrupted_checkpoint_lower_bound_count=sum(r.get("seconds_is_checkpoint_lower_bound", False) for r in group),
            sum_recorded_checkpoint_lower_bound_seconds=sum(r["seconds"] for r in group if r.get("seconds_is_checkpoint_lower_bound", False)),
            summed_worker_seconds=float(seconds.sum()),
            mean_seconds=float(seconds.mean()) if len(seconds) else None,
            median_seconds=float(np.median(seconds)) if len(seconds) else None,
            p90_seconds=float(np.quantile(seconds, .9)) if len(seconds) else None,
            maximum_seconds=float(seconds.max()) if len(seconds) else None)
    execution_path = directory / "execution.json"
    result["combined_execution"] = dict(workers=protocol["workers"],
        per_scan_seconds=protocol["per_scan_seconds"],
        elapsed_seconds=read(execution_path).get("seconds") if execution_path.exists() else None,
        durable_recovery_elapsed_seconds=read(execution_path).get("recovery_seconds") if execution_path.exists() else None,
        independent_evaluation_elapsed_seconds=time.monotonic() - started)
    write(directory / "evaluation.json", result)
    if ready:
        plot_results(rows, changes, directory)
    print(dict(available=len(ready), missing=protocol["missing_cases"], pending=len(pending),
               statistics=statistics), flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=OUT)
    parser.add_argument("--workers", type=int, default=30)
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    collect(args.run_dir, args.workers, args.allow_partial)


def plot_results(rows, changes, directory):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    available = [r for r in rows if r["status"] == "accepted"]
    available_scans = len({r["case"] for r in available})
    directory.mkdir(exist_ok=True, parents=True)

    def save(figure, stem):
        figure.tight_layout()
        for extension in ("png", "pdf"):
            figure.savefig(directory / f"{stem}.{extension}", dpi=175)
        plt.close(figure)

    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, arm in zip(axes, ARMS, strict=True):
        for method in METHODS:
            values = sorted(r["position_error_km_report_only"] for r in available
                            if r["arm"] == arm and r["method"] == method)
            ax.step(values, np.arange(1, len(values) + 1) / len(values), where="post",
                    color=COLORS[method], label=method.replace("_", " "))
        ax.axvline(.5, ls="--", color="black", lw=.8)
        ax.set(xlabel="Position error (km; log scale)", ylabel="Fraction of available scans",
               title=arm, xscale="log", ylim=(0, 1))
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    figure.suptitle(f"DS23 · {available_scans}/413 original members · position errors in both c arms\n"
                    "Unavailable scans excluded from CDF; original missing cases remain in the population")
    save(figure, "position_error_distributions")

    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for ax, arm in zip(axes, ARMS, strict=True):
        for method in METHODS:
            group = [r for r in available if r["arm"] == arm and r["method"] == method]
            ax.scatter([r["associated_original_percent"] for r in group],
                       [r["position_error_km_report_only"] for r in group],
                       s=14, alpha=.45, color=COLORS[method], label=method.replace("_", " "))
        ax.axhline(.5, ls="--", color="black", lw=.8)
        ax.set(xlabel="Unique original GLRT winners associated (%)",
               ylabel="Position error (km; log scale)", yscale="log", xlim=(0, 100), title=arm)
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    figure.suptitle(f"DS23 · {available_scans}/413 original members · association and position accuracy")
    save(figure, "association_percent_vs_error")

    figure, axes = plt.subplots(2, 2, figsize=(15, 8), sharex=True)
    for column, arm in enumerate(ARMS):
        for control, color in (("original_ALGO02", COLORS["original_ALGO02"]),
                               ("signed_prior", COLORS["signed_prior"])):
            group = [r for r in changes if r["arm"] == arm and r["control"] == control]
            xs = [int(r["case"].split("-")[1]) for r in group]
            axes[0, column].scatter(xs, [r["error_change_km"] for r in group],
                                    s=12, alpha=.6, color=color, label=control.replace("_", " "))
            axes[1, column].scatter(xs, [r["association_change_percentage_points"] for r in group],
                                    s=12, alpha=.6, color=color)
        axes[0, column].set(title=arm, ylabel="Position error change (km)")
        axes[1, column].set(xlabel="DS23 scan number", ylabel="Association change (percentage points)")
        for ax in axes[:, column]:
            ax.axhline(0, lw=.8, color="black"); ax.grid(alpha=.2)
        axes[0, column].legend(fontsize=8)
    figure.suptitle(f"DS23 · {available_scans}/413 original members · combined recovery minus control\n"
                    "Negative error change means closer to report GPS")
    save(figure, "per_scan_changes")

    figure, axes = plt.subplots(1, 2, figsize=(13, 5))
    for method in METHODS:
        group = [r for r in available if r["arm"] == "c0" and r["method"] == method]
        runtimes = [r["seconds"] for r in group if measured_runtime(r)]
        if runtimes:
            values = sorted(runtimes)
            axes[0].step(values, np.arange(1, len(values) + 1) / len(values), where="post",
                         color=COLORS[method], label=method.replace("_", " "))
        axes[1].scatter([r["original_GLRT_points"] for r in group if measured_runtime(r)],
                        [r["seconds"] for r in group if measured_runtime(r)],
                        s=14, alpha=.5, color=COLORS[method], label=method.replace("_", " "))
    axes[0].set(xlabel="Recorded method runtime (s; log scale)", xscale="log",
                ylabel="Fraction of scans with measured stage runtime")
    axes[1].set(xlabel="Original GLRT winners per scan", ylabel="Recorded method runtime (s; log scale)", yscale="log")
    for ax in axes:
        ax.grid(alpha=.2); ax.legend(fontsize=8)
    figure.suptitle("Archived controls and combined recovery · machine/load differ; inference time only\n"
                    "Interrupted checkpoint lower bounds excluded")
    save(figure, "runtime_comparison")


if __name__ == "__main__":
    main()
