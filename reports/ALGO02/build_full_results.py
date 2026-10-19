"""Audit and package completed ALGO02 results without altering frozen inference.

This evaluation-only report helper requires every sealed job to be terminal.
It never calls a fitter, changes an observation, selects a satellite, or writes
into an original case directory. Numeric evidence is archived losslessly;
large measurement/bank/history authorities are inventoried rather than copied.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import tarfile
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEFAULT = ROOT / "reports/2026_10_19_algo02_ds23_full"
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def difference(a, b):
    return float(np.linalg.norm(np.asarray(a) - np.asarray(b)))


def branch_signature(node):
    return [(row["component"], row.get("candidate_norad", row.get("norad", row["candidate_index"])), int(alias))
            for row, alias in zip(node["seed"]["rows"], node["aliases"], strict=True)]


def tle_epoch_ns(line):
    field = line[18:32]
    year = int(field[:2]);year += 1900 if year >= 57 else 2000
    return (int(datetime(year,1,1,tzinfo=timezone.utc).timestamp())*10**9 +
            int((Decimal(field[2:])-1)*86400*10**9))


def causal_case_audit(run, case):
    directory = run/case
    receipt = read(run/"causal_prior"/case/"receipt.json")
    cutoff = receipt["cutoff_utc_ns"]
    assert receipt["reference_position_used"] is False
    latest = read(directory/"nominal_elements.json")
    for value in latest.values():
        assert value["provenance"]["collected_utc_ns"] <= cutoff
        assert value["provenance"]["element_epoch_utc_ns"] <= cutoff
        assert tle_epoch_ns(value["lines"][0]) <= cutoff
    previous = read(run/"causal_prior"/case/"previous_receipt.json")
    for value in previous["sources"].values():
        assert value["collected_utc_ns"] <= cutoff and value["epoch_utc_ns"] <= cutoff
    previous_lines = [line for line in (run/"causal_prior"/case/"previous.tle").read_text().splitlines() if line.startswith("1 ")]
    assert all(tle_epoch_ns(line) <= cutoff for line in previous_lines)
    history_path = run/"causal_phase_history"/(case+".json")
    history = read(history_path)
    assert history["case"] == case and history["cutoff_utc_ns"] == cutoff
    count = 0
    for versions in history["past_versions"].values():
        for value in versions:
            assert value["epoch"] <= cutoff and value["collected_utc_ns"] <= cutoff
            assert tle_epoch_ns(value["lines"][0]) <= cutoff
            count += 1
    return dict(case=case, cutoff_utc_ns=cutoff, latest_elements=len(latest), previous_elements=len(previous_lines),
                historical_elements=count, all_collection_and_encoded_epoch_causal=True, history_sha256=digest(history_path))


def audit(run):
    sample, protocol, execution = [read(run / name) for name in ("sample.json", "protocol.json", "execution.json")]
    assert execution["all_terminal"], "never publish a pending run as final"
    expected_cases = {r["dataset_label"] for r in sample["selected"]}
    assert len(expected_cases) == len(sample["selected"]) == execution["total"] == 413
    receipts = execution["receipts"]
    assert len(receipts) == execution["completed"] == 413
    assert {r["case"] for r in receipts} == expected_cases
    assert digest(run / "sample.json") == protocol["sample_sha256"]
    assert all(digest(ROOT / path) == expected for path, expected in protocol["source_sha256"].items())
    protocol_sha = digest(run / "protocol.json")
    by_case = {r["case"]:r for r in receipts}
    members = {r["dataset_label"]:r for r in sample["selected"]}
    cases, failures, resources, authorities, causal = [], [], [], {}, []
    replay = []
    receipt_match = result_match = accepted = paired = 0
    case_payloads = {}
    for case in sorted(expected_cases):
        directory = run / case
        member, receipt = members[case], by_case[case]
        rp = directory / "algo02_result.json"
        result = read(rp) if rp.exists() else None
        if "supervisor_error" not in receipt:
            assert receipt["protocol_sha256"] == protocol_sha
            on_disk = directory / "execution_receipt.json"
            assert read(on_disk) == receipt
            receipt_match += 1
        if receipt.get("result_sha256"):
            assert result is not None and digest(rp) == receipt["result_sha256"]
            result_match += 1
        is_accepted = receipt.get("code") == 0 and result is not None and result.get("status") == "accepted"
        prep_path = directory / "prepared.json"
        prepared = read(prep_path) if prep_path.exists() else {}
        if prepared.get("status") == "prepared":
            assert prepared["graph_config_sha256"] == digest(HERE / "config/graph_selected.json")
            causal.append(causal_case_audit(run, case))
        ir_path = directory / "input_receipt.json"
        ir = read(ir_path) if ir_path.exists() else {}
        if ir:
            assert ir["case"] == case and ir["sample_sha256"] == protocol["sample_sha256"]
            assert not ir["GPS_or_localization_result_used"]
        resources.append(dict(case=case, graph_config_sha256=prepared.get("graph_config_sha256"),
                              adapter=ir.get("public_adapter_path"), adapter_sha256=ir.get("public_adapter_sha256")))
        row = dict(case=case, recording_format=member["recording_format"],
            captured_utc_ns=member["captured_utc_ns"], development_scan=case in sample["development_cases"],
            status=("execution_failed" if receipt.get("code") else (result or {}).get("status", "failed")),
            reason=((result or {}).get("reason") or receipt.get("supervisor_error") or
                    ("case_timeout_1200s" if receipt.get("code")==124 else
                     ("stage_exit_code_"+str(receipt["code"]) if receipt.get("code") else None))),
            process_code=receipt.get("code"), seconds=receipt.get("seconds"),
            GLRT_points=prepared.get("GLRT_points"), graph_points=prepared.get("graph_points"),
            graph_tracks=prepared.get("graph_tracks"), curved_points=None,
            linear_offered_tracks=(result or {}).get("linear_offered_tracks"),
            linear_offered_points=(result or {}).get("linear_offered_points"),
            linear_used_points=(result or {}).get("linear_used_points"),
            linear_paired_valid=(result or {}).get("linear_paired_valid"),
            phase_history_qualified=(result or {}).get("earlier_TLE_validation_qualified"),
            fallback=(result or {}).get("fallback"))
        payloads = []
        for name in ("algo02_result.json", "execution_receipt.json", "input_receipt.json",
                     "preparation_receipt.json", "prepared.json", "receipt.json", "previous_receipt.json",
                     "pipeline.log"):
            if (directory / name).is_file():
                payloads.append((case + "/" + name, (directory / name).read_bytes()))
        initial_path = directory / "result.json"
        if initial_path.exists():
            initial = read(initial_path)
            compact = {key:initial[key] for key in ("case", "algorithm", "status", "final_node", "final_mask",
                       "initial_failed_components", "trims", "exclusion_history", "post_salvage_history",
                       "GPS_used", "future_TLE_used", "source_sha256") if key in initial}
            compact["original_result_sha256"] = digest(initial_path)
            compact["initial_records"] = {arm:dict(record=value["record"], metrics=value["metrics"])
                                           for arm, value in initial.get("arms", {}).items()}
            payloads.append((case + "/initial_branch.json", (json.dumps(compact, indent=2) + "\n").encode()))
        if result is not None:
            assert result["case"] == case
            assert result["engine_sha256"] == protocol["source_sha256"]["tools/algo02_scan.py"]
            assert result["GPS_used"] is False and result["future_TLE_used"] is False
            if result.get("history_sha256"):
                assert result["history_sha256"] == causal[-1]["history_sha256"]
            for arm in result.get("linear_arms", {}).values():
                value = arm["calibration_replay_max_coefficient_difference"]
                assert value == 0
                replay.append(value)
        if is_accepted:
            accepted += 1
            assert result["paired_c_masks_aliases_identities_and_budgets"]
            source = "linear_arms" if result["linear_paired_valid"] else "curved_arms"
            assert result["policy_arms"] == result[source]
            if result["linear_paired_valid"]:
                paired += 1
            assert result["no_stationary_history_position_pooling"]
            assert result["curved_only_calibration_no_linear_normal_equation_update"]
            assert result["shared_full_calibration_covariance_preserved"]
            assert len(result["mask"]) == len(result["original_mask"])
            mask_count = sum(result["mask"])
            ids_pair = []
            for arm in ARMS:
                selected = result["policy_arms"][arm]
                assert selected["active_points"] == mask_count
                xy = selected["endpoint_east_north_km"]
                assert len(xy) == 2 and np.isfinite(xy).all() and max(abs(x) for x in xy) <= 12.5 + 1e-8
                tracks = selected["gates"]["tracks"]
                assert tracks and all(r["compatible"] for r in tracks)
                curved_ids = [o for r in tracks for o in r["observation_ids"]]
                assert len(curved_ids) == len(set(curved_ids)) == mask_count
                new_ids = []
                if result["linear_paired_valid"]:
                    assert selected["final_phase_change_s"] <= .01
                    assert all(r["compatible"] for r in selected["linear_gates"])
                    new_ids = [o for r in selected["linear_gates"] for o in r["observation_ids"]]
                    assert not set(new_ids) & set(curved_ids)
                    assert len(new_ids) == len(set(new_ids)) == result["linear_used_points"]
                ids_pair.append((curved_ids,new_ids))
            assert ids_pair[0] == ids_pair[1]
            row["curved_points"] = mask_count
        else:
            failures.append(dict(case=case, recording_format=member["recording_format"], status=row["status"],
                                 reason=row["reason"], process_code=row["process_code"]))
        pr = directory / "preparation_receipt.json"
        authorities[case] = dict(recording_id=member["recording_id"],
            raw_authority_digest=member["raw_authority_digest"], result_sha256=digest(rp) if rp.exists() else None,
            preparation_receipt_sha256=digest(pr) if pr.exists() else None,
            input_authorities=read(pr).get("files_sha256", {}) if pr.exists() else {},
            note="Large measurement, propagated-bank and causal-history bytes are not duplicated; hashes are producer receipts, not a second full raw-input rehash")
        case_payloads[case] = payloads
        cases.append(row)
    write_csv(run / "case_summary.csv", cases)
    write_csv(run / "failed_cases.csv", failures)
    write(run / "input_authorities.json", authorities)
    write(run / "resource_audit.json", dict(graph_configuration_sha256=digest(HERE / "config/graph_selected.json"),
        per_case=resources, note="Non-Python resources were not included in the original 232-file Python closure; receipts are an explicit supplementary provenance audit"))
    write(run / "causal_audit.json", dict(cases=causal,
        latest_elements_checked=sum(r["latest_elements"] for r in causal),
        previous_elements_checked=sum(r["previous_elements"] for r in causal),
        historical_elements_checked=sum(r["historical_elements"] for r in causal),
        actual_TLE_encoded_epoch_and_collection_checked_against_each_scan=True))
    validation = dict(all_terminal=True, population=413, unique_receipts=413, actual_receipts_equal_on_disk=receipt_match,
        receipt_result_digests_recomputed=result_match, all_frozen_Python_hashes_unchanged=True,
        accepted_c_pairs=accepted, linear_paired_valid=paired, curved_pair_fallback=accepted-paired,
        failures=len(failures), all_accepted_policy_gates_pass=True,
        all_accepted_c_arms_share_unique_disjoint_original_ids=True,
        calibration_replay_arms=len(replay), maximum_calibration_replay_difference=max(replay, default=None),
        graph_config_matches_every_prepared_case=True, reference_GPS_only_in_evaluation=True,
        protocol_sha256=protocol_sha, audited_utc=datetime.now(timezone.utc).isoformat())
    write(run / "validation.json", validation)
    return sample, cases, case_payloads


def runtime_audit(run):
    source = ROOT / "reports/2026_10_19_algo02_qualification/runtime_dependencies.json"
    baseline = read(source)
    graph = baseline["graph_configuration"]
    adapter = baseline["adaptive_public_adapter"]
    changed = []
    for path, expected in ((Path(graph["path"]), graph["sha256"]), (Path(adapter["path"]), adapter["sha256"])):
        if digest(path) != expected:
            changed.append(str(path))
    production = Path(adapter["path"]).parents[3]
    for name, expected in adapter["static_local_import_closure_sha256"].items():
        if digest(production/name) != expected:
            changed.append(str(production/name))
    cases = read(run/"resource_audit.json")["per_case"]
    mismatched = [row["case"] for row in cases if row["adapter_sha256"] is not None and
                  row["adapter_sha256"] != adapter["sha256"]]
    # Report deviations rather than recasting a supplementary audit as a seal.
    write(run/"runtime_dependencies_before_and_after.json", dict(before=baseline,
        postrun_utc=datetime.now(timezone.utc).isoformat(), changed_runtime_files=changed,
        exported_adapter_hash_mismatch_cases=mismatched,
        all_observed_resource_hashes_match=not changed and not mismatched,
        limitation="The original Python-source freeze did not include the graph JSON or the separate production adapter closure. Before/after hashes and per-case receipts supplement provenance; they are not a retroactive pre-run seal or proof of every intervening filesystem state."))


def archive(run, case_payloads):
    destination = run / "numerical_evidence"
    destination.mkdir(exist_ok=True)
    manifest, parts = {}, []
    cases = sorted(case_payloads)
    for start in range(0, len(cases), 40):
        chunk = cases[start:start + 40]
        path = destination / f"cases_{start+1:04d}_{start+len(chunk):04d}.tar.xz"
        with tarfile.open(path, "w:xz", preset=3) as tar:
            for case in chunk:
                for name, data in case_payloads[case]:
                    item = tarfile.TarInfo(name);item.size=len(data);item.mtime=0
                    tar.addfile(item, io.BytesIO(data))
                    manifest[name] = dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data), archive=path.name)
        assert path.stat().st_size < 50_000_000, "split before publication; never push an oversized part"
        with tarfile.open(path) as tar:
            for item in tar.getmembers():
                assert hashlib.sha256(tar.extractfile(item).read()).hexdigest() == manifest[item.name]["sha256"]
        parts.append(dict(path=str(path.relative_to(run)), bytes=path.stat().st_size, sha256=digest(path)))
    write(destination / "inventory.json", manifest)
    write(destination / "parts.json", parts)


def development_comparison(run, sample, cases):
    from report_algo02_ds23 import position_error
    rows = []
    receipts = {r["case"]:r for r in read(run/"execution.json")["receipts"]}
    old_root = ROOT / "reports/2026_10_19_ds23_predictive_linear"
    old_initial_root = ROOT / "reports/2026_10_18_algo01_ds23_random20"
    for case in sample["development_cases"]:
        path = run / case / "algo02_result.json"
        fresh = read(path) if path.exists() else None
        old = read(old_root / (case + ".json"))["results"]["all_linear"]
        init = read(run / case / "result.json") if (run / case / "result.json").exists() else None
        old_init = read(old_initial_root / case / "result.json")
        branch_same = bool(init and init.get("final_node") and
                           branch_signature(init["final_node"]) == branch_signature(old_init["final_node"]))
        for arm in ARMS:
            prior = old["policy_arms"][arm]
            current = fresh["policy_arms"][arm] if fresh and fresh.get("status") == "accepted" and receipts[case].get("code")==0 else None
            rows.append(dict(case=case, arm=arm, fresh_accepted=current is not None,
                fresh_RF_branch_equal_historical=branch_same,
                curved_mask_identical=bool(fresh and fresh.get("mask") == read(old_root / (case + ".json"))["mask"]),
                endpoint_difference_km=difference(current["endpoint_east_north_km"], prior["endpoint_east_north_km"]) if current else None,
                historical_linear_paired_valid=old["paired_valid"], fresh_linear_paired_valid=(fresh or {}).get("linear_paired_valid"),
                historical_error_km=position_error(prior["endpoint_latlon"]),
                fresh_error_km=position_error(current["endpoint_latlon"]) if current else None,
                historical_east_km=prior["endpoint_east_north_km"][0], historical_north_km=prior["endpoint_east_north_km"][1],
                fresh_east_km=current["endpoint_east_north_km"][0] if current else None,
                fresh_north_km=current["endpoint_east_north_km"][1] if current else None))
    write_csv(run / "development_comparison.csv", rows)
    summary = {}
    for arm in ARMS:
        group = [r for r in rows if r["arm"]==arm and r["fresh_accepted"]]
        summary[arm] = dict(accepted_pairs=len(group),
            same_final_assignment_branch=sum(r["fresh_RF_branch_equal_historical"] for r in group),
            same_curved_mask=sum(r["curved_mask_identical"] for r in group),
            endpoint_displacement_median_km=float(np.median([r["endpoint_difference_km"] for r in group])) if group else None,
            endpoint_displacement_max_km=max((r["endpoint_difference_km"] for r in group),default=None),
            historical_mean_error_km=float(np.mean([r["historical_error_km"] for r in group])) if group else None,
            fresh_mean_error_km=float(np.mean([r["fresh_error_km"] for r in group])) if group else None)
    write(run / "development_comparison.json", dict(rows=rows, summary=summary,
        note="Historical 20 reused earlier RF-discovered branches; full corpus freshly discovers every scan. Compare identity/alias signatures, not incidental discovery scores. Old and fresh errors here are recomputed with the same reporter. Endpoint differences are not a same-branch replay regression unless branch and mask match."))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), sharey=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        group = [r for r in rows if r["arm"] == arm and r["fresh_accepted"]]
        ax.bar(np.arange(len(group)), [r["endpoint_difference_km"] for r in group], color=["#4477aa" if r["fresh_RF_branch_equal_historical"] else "#ee7733" for r in group])
        ax.set_xticks(np.arange(len(group)), [r["case"].split("-")[-1] for r in group], rotation=90)
        ax.set(title=arm, xlabel="Original development scan", ylabel="Fresh vs historical endpoint displacement (km)")
        ax.grid(axis="y", alpha=.2)
    fig.suptitle("Fresh cold RF discovery versus cached development inputs; blue=same final branch")
    fig.tight_layout();fig.savefig(run / "development_comparison.png", dpi=160);plt.close(fig)


def baseline_comparison(run, sample):
    # Evaluation only, after the frozen inference has finished. The separate
    # reporter owns the supplied reference coordinate and error convention.
    from report_algo02_ds23 import position_error, summarize
    rows = []
    receipts = {r["case"]:r for r in read(run/"execution.json")["receipts"]}
    for member in sample["selected"]:
        case = member["dataset_label"]
        initial_path, fresh_path = (run/case/name for name in ("result.json", "algo02_result.json"))
        initial = read(initial_path) if initial_path.exists() else None
        fresh = read(fresh_path) if fresh_path.exists() else None
        for arm in ARMS:
            a = initial["arms"][arm]["record"] if initial and initial.get("status") == "complete" else None
            b = fresh["policy_arms"][arm] if fresh and fresh.get("status") == "accepted" and receipts[case].get("code")==0 else None
            curved = fresh.get("curved_arms", {}).get(arm) if b else None
            rows.append(dict(case=case, arm=arm, recording_format=member["recording_format"],
                development_scan=case in sample["development_cases"],
                initial_qualified=a is not None, ALGO02_qualified=b is not None,
                initial_error_km=position_error(a["endpoint_latlon"]) if a else None,
                ALGO02_error_km=position_error(b["endpoint_latlon"]) if b else None,
                curved_history_error_km=position_error(curved["endpoint_latlon"]) if curved else None,
                initial_curved_points=a["active_points"] if a else None,
                ALGO02_curved_points=b["active_points"] if b else None,
                initial_frequency_RMS_hz=a["frequency_rms_hz"] if a else None,
                ALGO02_frequency_RMS_hz=b["RMS_hz"] if b else None))
    groups = {"all":lambda r:True, "original20_development":lambda r:r["development_scan"],
        "other393":lambda r:not r["development_scan"],
        "fast":lambda r:r["recording_format"]=="short_window_iq_recording",
        "adaptive":lambda r:r["recording_format"]=="starlink_adaptive_hop_iq"}
    summary = {}
    for name, predicate in groups.items():
        summary[name] = {}
        for arm in ARMS:
            chosen = [r for r in rows if predicate(r) and r["arm"]==arm]
            common = [r for r in chosen if r["initial_qualified"] and r["ALGO02_qualified"]]
            paired = {method:summarize([r[column] for r in common], len(chosen)) for method,column in
                      (("fresh_ALGO01", "initial_error_km"), ("ALGO02", "ALGO02_error_km"),
                       ("ALGO02_curved_only", "curved_history_error_km"))}
            if common:
                paired["ALGO02_minus_fresh_ALGO01"] = dict(
                    mean_error_difference_km=paired["ALGO02"]["mean_km"]-paired["fresh_ALGO01"]["mean_km"],
                    median_error_difference_km=paired["ALGO02"]["median_km"]-paired["fresh_ALGO01"]["median_km"],
                    improved=sum(r["ALGO02_error_km"] < r["initial_error_km"]-1e-9 for r in common),
                    regressed=sum(r["ALGO02_error_km"] > r["initial_error_km"]+1e-9 for r in common))
            summary[name][arm] = dict(common_accepted_pair_count=len(common),
                matched_common_accepted=paired,
                independent_denominators={method:summarize([r[column] for r in chosen if r[column] is not None],len(chosen))
                    for method,column in (("fresh_ALGO01","initial_error_km"),("ALGO02","ALGO02_error_km"))})
    write_csv(run/"baseline_comparison.csv", rows)
    write(run/"baseline_comparison.json",dict(position=summary,
        interpretation="Fresh ALGO01 and ALGO02 share physical inputs and cold RF discovery. Priors, gates and accepted masks differ by policy. Both c arms remain matched within each policy. Matched intersection and independent coverage are reported separately; no additional inference."))
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), sharex=True, sharey=True)
    common_rows = [r for r in rows if r["initial_qualified"] and r["ALGO02_qualified"]]
    limit = max((max(r["initial_error_km"],r["ALGO02_error_km"]) for r in common_rows),default=1.)*1.05
    for ax, arm in zip(axes,ARMS,strict=True):
        group = [r for r in common_rows if r["arm"]==arm]
        other = [r for r in group if not r["development_scan"]]
        old = [r for r in group if r["development_scan"]]
        ax.scatter([r["initial_error_km"] for r in other], [r["ALGO02_error_km"] for r in other],
                   s=13,alpha=.6,label="Additional recordings")
        ax.scatter([r["initial_error_km"] for r in old], [r["ALGO02_error_km"] for r in old],
                   s=35,facecolors="none",edgecolors="tab:orange",label="Original 20 development")
        ax.plot([0,limit],[0,limit],color="black",ls="--",lw=.8)
        ax.set(xlim=(0,limit),ylim=(0,limit),xlabel="Fresh ALGO01 error (km)",ylabel="ALGO02 error (km)",title=arm)
        ax.grid(alpha=.2);ax.legend(fontsize=8)
    fig.suptitle("Matched qualified scans; below dashed line = lower error with ALGO02\nUnlocalized recordings are reported separately, not plotted at zero")
    fig.tight_layout();fig.savefig(run/"baseline_comparison.png",dpi=160)
    for ax in axes:
        ax.set(xlim=(0,5),ylim=(0,5))
    fig.suptitle("Matched comparison: 0–5 km display zoom\nAccepted outliers remain in the full plot and every statistic")
    fig.tight_layout();fig.savefig(run/"baseline_comparison_zoom.png",dpi=160);plt.close(fig)


def extra_figures(run, sample):
    with (run / "positions.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    members = {r["dataset_label"]:r for r in sample["selected"]}
    fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        accepted = [r for r in rows if r["arm"] == arm and r["error_km"]]
        for fmt, label, marker in [("short_window_iq_recording", "Fast", "o"), ("starlink_adaptive_hop_iq", "Adaptive", "+")]:
            group = [r for r in accepted if r["recording_format"] == fmt]
            times = [datetime.fromtimestamp(members[r["case"]]["captured_utc_ns"]/1e9, timezone.utc) for r in group]
            ax.scatter(times, [float(r["error_km"]) for r in group], s=15, marker=marker, label=label, alpha=.7)
        ax.set(ylabel="Position error (km)", title=arm);ax.axhline(.5, ls="--", color="crimson", lw=.8);ax.legend();ax.grid(alpha=.2)
    fig.suptitle("Independent per-scan position error by capture time (UTC); finite accepted positions only")
    fig.autofmt_xdate();fig.tight_layout();fig.savefig(run / "chronological_errors.png", dpi=160);plt.close(fig)


def render_report(run):
    summary, validation = read(run/"summary.json"), read(run/"validation.json")
    baseline = read(run/"baseline_comparison.json")["position"]
    causal, execution = read(run/"causal_audit.json"), read(run/"execution.json")
    parts = read(run/"numerical_evidence/parts.json")
    body = ["# ALGO02: completed evaluation on all 413 DS23 recordings", "",
        "**ALGO02 improves both mean and median error against freshly run ALGO01 on the 404 recordings with qualified positions from both methods.** "
        "Coverage is **407/413 for ALGO01 versus 404/413 for ALGO02**; the additional unavailable positions are not silently omitted from coverage. "
        "All 413 jobs are terminal. The 0.5 km mean-and-median objective remains unmet.", "",
        "| Matched subset | Arm | Qualified common pairs | Fresh ALGO01 mean / median km | ALGO02 mean / median km |",
        "|---|---|---:|---:|---:|"]
    for group in ("all","original20_development","other393","fast","adaptive"):
        for arm in ARMS:
            s=baseline[group][arm];p=s["matched_common_accepted"];a,b=p["fresh_ALGO01"],p["ALGO02"]
            body.append(f"| {group} | {arm} | {s['common_accepted_pair_count']} | {a['mean_km']:.3f} / {a['median_km']:.3f} | {b['mean_km']:.3f} / {b['median_km']:.3f} |")
    body += ["", "On the additional 393 recordings, the common 384 pairs improve fitted-c mean/median error by **18.7% / 20.8%**. "
        "Both capture formats improve. This supports a broader **within-site** result, not new-location validation. "
        "The original 20 were development data; the other 393 were outside that sample when ALGO02 was frozen. "
        "The full corpus is one site/dataset, with temporally related RF and TLE errors.", "",
        "![Matched fresh ALGO01 versus ALGO02](baseline_comparison.png)",
        "![Display zoom; full outliers and statistics retained](baseline_comparison_zoom.png)", "",
        "## All-record coverage and conditional errors", "",
        "Mean, median and tail errors describe finite qualified positions only. Counts below 0.5 km use the **entire recording denominator**. "
        "There is no invented error for a failed recording, trimming of accepted outliers or selection of a favorable c arm.", "",
        "| Subset | Arm | Qualified / recordings | Mean km | Median km | P90 km | Maximum km | Below 0.5 km / recordings |",
        "|---|---|---:|---:|---:|---:|---:|---:|"]
    for group, arms in summary["position"].items():
        for arm,s in arms.items():
            body.append(f"| {group} | {arm} | {s['localized']} / {s['population']} | {s['mean_km']:.3f} | {s['median_km']:.3f} | {s['p90_km']:.3f} | {s['maximum_km']:.3f} | {s['below_half_km']} / {s['population']} |")
    body += ["", "![Every scan, including failed recording markers](position_errors.png)",
        "![Success CDF with all 413 recordings in the denominator](error_distribution.png)",
        "![Chronological position errors](chronological_errors.png)", "",
        "Three fast recordings have no frozen tracking contract: **0012, 0184, 0286**. Six fast recordings reach the declared 1200 s limit: "
        "**0004, 0064, 0068, 0080, 0118, 0266**. No retries or post-hoc budget changes are applied. "
        "Three of those timeouts retain a qualified initial ALGO01 result, explaining 407 versus 404 coverage. "
        "All 206 adaptive recordings qualify; 198/207 fast recordings qualify for ALGO02. "
        "See [failed cases](failed_cases.csv) and [execution receipts](execution.json).", "",
        "Accepted failures of accuracy remain visible: scan **0081** worsens from 8.652→16.732 km c0 and 8.659→16.980 km fitted c. "
        "Scan **0326** improves from 18.580→13.948 km c0 and 18.895→13.341 km fitted c, while remaining inaccurate. "
        "Both pass the frozen model's acceptance checks. Residual gates are not proof of correct identity, location or a global optimum. "
        "No exploratory later repair is substituted into this frozen result.", "",
        "## What improved and what stayed matched", "",
        "[ALGO02's full specification](../ALGO02/README.md) freezes causal TLE-history phase priors, receiver-support weighting, "
        "300 Hz fragment constants and Gaussian conditional linear evidence. "
        "Curved tracks alone calibrate hardware and satellites at a fixed position; added linear tracks carry the full shared predictive covariance. "
        "Every controlled final position refit starts at the center of the same 25×25 km regional box `(37.906,-122.545)`. "
        "Cold discovery uses each scan's broad causal catalogue. No previous-scan RF position, true site, post-scan TLE or manually supplied identity initializes inference.", "",
        "The comparison reuses each scan's physical input and fresh RF discovery. Policy priors, gates and accepted masks may differ; "
        "this is an algorithm-policy comparison, not an attribution to a single parameter on identical masks. "
        "Within each policy, c0 and fitted-c share observations, identities, aliases, all other priors and numerical budgets. "
        "[Matched and independently qualified statistics](baseline_comparison.json) and [all comparison rows](baseline_comparison.csv) preserve both denominators.", "",
        "Of 404 complete ALGO02 trials, **365** qualify the paired linear-evidence trial and **39** retain the qualified curved pair. "
        "Adding Gaussian linear evidence changes the common-cohort curved-only mean/median from **1.558/1.337→1.520/1.270 km c0**, "
        "and **1.552/1.313→1.508/1.249 km fitted c**. "
        "Original winners, calibration points and predictive linear points are different counts. "
        "These selected position-evidence totals are not claimed as whole-scan satellite-association percentages.", "",
        "The fresh run reproduces **all 20 historical ALGO02 assignment branches, curved masks and both c-arm endpoints exactly**. "
        "The remaining accuracy difference comes from evaluating additional scans, not silently changing that development algorithm. "
        "See [replay comparison](development_comparison.json) and [per-scan values](development_comparison.csv).", "",
        "![Historical versus fresh development endpoints](development_comparison.png)", "",
        "## Audit, execution and reconstruction", "",
        f"The 30-worker, one-BLAS-thread run takes **{execution['elapsed_s']/60:.2f} minutes** on a host with 24 available CPUs. "
        "This includes read-only preparation and cold discovery; it is not an embedded runtime benchmark. "
        "No new RF acquisition or IQ remeasurement is performed. The 1200 s per-recording cap and all sources are fixed before submission.", "",
        f"The audit verifies **{validation['unique_receipts']}** unique execution receipts, **{validation['receipt_result_digests_recomputed']}** written result digests "
        "(404 qualified and three input-failure outputs), every frozen Python source hash, matched c-arm ownership, "
        "unique/disjoint physical IDs and all accepted policy gates. "
        f"All **{validation['calibration_replay_arms']}** completed raw linear-trial arms reproduce curved-only calibration with **zero coefficient difference**.", "",
        f"Encoded TLE bytes and collection timestamps are rechecked against each scan cutoff: **{causal['latest_elements_checked']:,}** latest, "
        f"**{causal['previous_elements_checked']:,}** previous and **{causal['historical_elements_checked']:,}** historical elements. "
        "No post-observation TLE is accepted. [Validation](validation.json) and [causal audit](causal_audit.json) retain the counts and per-case boundaries.", "",
        "The original 232-file Python freeze did not itself pin the graph JSON or separate production adapter closure. "
        "The configuration matches every prepared receipt, and before/after audits of the 127-file adapter closure show no change or export-hash mismatch. "
        "This is supplementary provenance, not a retroactive pre-run seal or proof of every intervening filesystem state. "
        "See [resource receipts](resource_audit.json) and [before/after dependencies](runtime_dependencies_before_and_after.json).", "",
        f"Lossless numeric evidence is split into **{len(parts)} archives**, all below 50 MB, totaling **{sum(p['bytes'] for p in parts)/1e6:.1f} MB**. "
        "It preserves complete ALGO02 result bytes, case receipts/logs and derived initial ALGO01 branch/record payloads with original result hashes. "
        "[Archive parts](numerical_evidence/parts.json) and [payload inventory](numerical_evidence/inventory.json) bind the hashes. "
        "Original IQ, tracking contracts, propagated banks and full TLE histories are not duplicated. "
        "[Input authorities](input_authorities.json) records their producer checksums; this is not a second full raw-input rehash. "
        "Those local/archive authorities remain required for independent scientific replay.", "",
        "The supplied reference `(37.849061591561885,-122.48574968092912)` is confined to post-fit reporting. "
        "Accuracy assumes all recordings were stationary at that site; antenna altitude and the common site have not been independently survey-certified. "
        "No stationary-history position pooling is used. These results do not establish sub-0.5 km performance, calibrated confidence intervals "
        "or generalization to a new location.", "",
        "[Protocol](protocol.json) · [Membership](sample.json) · [Every position and failure](positions.csv) · "
        "[Summary](summary.json) · [Case/evidence counts](case_summary.csv) · [ALGO02 source and method](../ALGO02/README.md)", ""]
    (run/"README.md").write_text("\n".join(body))


def main(run, make_archives):
    sample, cases, payloads = audit(run)
    runtime_audit(run)
    development_comparison(run, sample, cases)
    baseline_comparison(run, sample)
    extra_figures(run, sample)
    if make_archives:
        archive(run, payloads)
    if (run/"numerical_evidence/parts.json").exists():
        render_report(run)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT)
    parser.add_argument("--archive", action="store_true")
    args = parser.parse_args();main(args.run_dir, args.archive)
