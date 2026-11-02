"""Independent causal receipt/decision audit; never optimize or read geography."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
from sgp4.api import Satrec

ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent
OLD = REPORT.parent / "2026_11_02_generalized_corrections"
ARMS = ("c0", "fitted_c")
MINIMUMS = {"Age3": 3, "Age2": 2}


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def element_sha(lines):
    return hashlib.sha256(("\n".join(lines) + "\n").encode()).hexdigest()


def epoch(lines):
    satellite = Satrec.twoline2rv(*lines)
    return round((satellite.jdsatepoch - 2440587.5 + satellite.jdsatepochF) * 86400e9)


def bounded_covariance(coefficients):
    a = np.asarray(coefficients, float)
    require(a.ndim == 2 and a.shape[1] == 3 and len(a) > 0 and np.isfinite(a).all(), "Invalid physical coefficients")
    second = a.T @ a / len(a)
    eigen, vectors = np.linalg.eigh(.5 * np.eye(3) + .5 * second)
    covariance = (vectors * np.clip(eigen, 1., 16.)) @ vectors.T
    return second, (covariance + covariance.T) / 2


def independent_pairs(versions, nominal_epoch, cutoff, horizon):
    """Exhaustive disjoint matching, independent of the candidate module."""
    oldest = cutoff - int(72 * 3.6e12)
    unique = {}
    for row in versions:
        if oldest <= row["epoch"] <= nominal_epoch and oldest <= row["collected_utc_ns"] <= cutoff:
            key = row["epoch"]
            if key not in unique or (row["collected_utc_ns"], element_sha(row["lines"])) < (unique[key]["collected_utc_ns"], element_sha(unique[key]["lines"])):
                unique[key] = row
    rows = sorted(unique.values(), key=lambda r: (r["epoch"], element_sha(r["lines"])))
    edges = {}
    for i, older in enumerate(rows):
        for j, newer in enumerate(rows[i + 1:], i + 1):
            error = abs((newer["epoch"] - older["epoch"]) / 3.6e12 - horizon)
            if error <= max(2., .25 * horizon) and older["collected_utc_ns"] <= newer["epoch"]:
                edges[i, j] = error

    @lru_cache(None)
    def enumerate_matchings(remaining):
        if not remaining:
            return ()
        i, *rest = remaining
        rest = tuple(rest)
        choices = [enumerate_matchings(rest)]
        for j in rest:
            if (i, j) in edges:
                choices.append(((i, j),) + enumerate_matchings(tuple(k for k in rest if k != j)))
        return min(choices, key=lambda pairs: (-len(pairs), sum(edges[p] for p in pairs), pairs))

    return [(rows[i], rows[j]) for i, j in enumerate_matchings(tuple(range(len(rows))))]


def audit_prior(record, receipt):
    family = record["target_family"]
    require(receipt.get("target_family", receipt.get("selected_family")) == family, "Prior target differs")
    if family is None:
        require(receipt["status"] != "ready", "Unnominated ready prior")
        return dict(case=record["case"], status=receipt["status"], history_checked=False)
    # Failed physical projections can still retain causal metadata. All ready
    # receipts must bind all three source files and the complete selected pairs.
    if receipt["status"] != "ready":
        return dict(case=record["case"], status=receipt["status"], history_checked=False)
    z = read(record["input_path"])
    for key in ("history", "nominal_elements", "temporal_extent"):
        require(sha(receipt[key + "_path"]) == receipt[key + "_sha256"], "Causal source changed: " + key)
    raw = read(receipt["history_path"])
    nominal = read(receipt["nominal_elements_path"])[str(family)]
    cutoff, origin = z["scan_receipt"]["cutoff_utc_ns"], z["scan_receipt"]["origin_utc_ns"]
    require(raw["cutoff_utc_ns"] == cutoff and raw["origin_utc_ns"] == origin and cutoff <= origin, "History timing differs")
    require(raw["latest_elements_sha256"] == receipt["nominal_elements_sha256"], "History nominal binding differs")
    sources = {(s["collected_utc_ns"], s["sha256"].removeprefix("sha256:")) for s in raw["sources"]}
    nominal_epoch = epoch(nominal["lines"])
    provenance = nominal.get("provenance", nominal)
    ndigest = provenance["snapshot_digest"].removeprefix("sha256:")
    require(int(Satrec.twoline2rv(*nominal["lines"]).satnum) == family, "Nominal satellite differs")
    require(nominal_epoch <= cutoff and provenance["collected_utc_ns"] <= cutoff, "Nominal unavailable at RF cutoff")
    require(any(t <= provenance["collected_utc_ns"] and h == ndigest for t, h in sources), "Nominal snapshot not available by receipt")
    require(abs(provenance.get("element_epoch_utc_ns", nominal_epoch) - nominal_epoch) <= 2048, "Nominal bytes/epoch differ")
    versions = raw["past_versions"][str(family)]
    by_element = {}
    for version in versions:
        require(version["epoch"] <= cutoff and version["collected_utc_ns"] <= cutoff, "Historical element unavailable at cutoff")
        require((version["collected_utc_ns"], version["snapshot_sha256"].removeprefix("sha256:")) in sources, "Historical snapshot lacks source receipt")
        require(int(Satrec.twoline2rv(*version["lines"]).satnum) == family, "Historical satellite differs")
        require(abs(epoch(version["lines"]) - version["epoch"]) <= 2048, "Historical bytes/epoch differ")
        by_element[(element_sha(version["lines"]), version["collected_utc_ns"])] = version
    times = np.asarray([r["time_s"] for r in read(receipt["temporal_extent_path"])])
    midpoint, duration = float((times.min() + times.max()) / 2), float(np.ptp(times))
    horizon = (origin + round(midpoint * 1e9) - nominal_epoch) / 3.6e12
    require(abs(receipt["nominal_horizon_hours"] - horizon) < 1e-10, "Nominal forecast horizon differs")
    require(abs(receipt["historical_arc_duration_s"] - duration) < 1e-10, "Historical arc length differs")
    matching = independent_pairs(versions, nominal_epoch, cutoff, horizon)
    projections = receipt["historical_pair_projections"]
    require(len(matching) == len(projections) == receipt["pair_count"] >= 2, "Disjoint match count differs")
    coefficients, scales = [], np.asarray(receipt["current_mode_SD"])
    require(scales.shape == (3,) and np.isfinite(scales).all() and (scales > 0).all(), "Invalid physical SDs")
    for (older, newer), detail in zip(matching, projections):
        for name, version in (("older", older), ("newer", newer)):
            saved = detail[name]
            require((saved["element_sha256"], saved["collected_utc_ns"]) in by_element, "Projected element absent from source history")
            require(saved == dict(element_sha256=element_sha(version["lines"]), epoch_utc_ns=version["epoch"], collected_utc_ns=version["collected_utc_ns"], snapshot_sha256=version["snapshot_sha256"]), "Exact disjoint matching differs")
        a = np.asarray(detail["coefficients"])
        require(np.allclose(np.asarray(detail["physical_parameter_revision"]), a * scales, rtol=1e-12, atol=1e-12), "Physical revision transport differs")
        require(detail["current_mode_SD"] == receipt["current_mode_SD"] and detail["physical_parameter_units"] == ["rev/day", "deg", "deg"], "Physical coordinates differ")
        require(detail["historical_derivative_anchor_utc_ns"] == newer["epoch"], "Historical derivative anchor differs")
        require(np.allclose(detail["historical_arc_times_s"], [-duration / 2, 0., duration / 2], atol=1e-10), "Historical derivative arc differs")
        require(detail["alignment_converged"] and 1 <= detail["alignment_steps"] <= 8 and abs(detail["final_alignment_step_s"]) < 1e-7 and abs(detail["phase_alignment_s"]) <= 120, "Historical phase alignment fails")
        singular = np.asarray(detail["column_normalized_singular_values"])
        require(np.isfinite(singular).all() and singular.min() >= singular.max() * 1e-8 and np.min(detail["column_norms"]) > 1e-14, "Physical basis rank fails")
        coefficients.append(a)
    represented = 1 - sum(p["projection_residual_energy_km2"] for p in projections) / max(sum(p["phase_removed_state_energy_km2"] for p in projections), 1e-30)
    require(abs(represented - receipt["represented_energy_fraction"]) < 1e-12 and represented >= .5, "History projection unsupported")
    second, covariance = bounded_covariance(coefficients)
    require(np.allclose(second, receipt["second_moment"], rtol=1e-12, atol=1e-12), "Uncentered second moment differs")
    require(np.allclose(covariance, receipt["coefficient_covariance"], rtol=1e-12, atol=1e-12), "Fixed zero-mean covariance differs")
    require(receipt["current_derivative_anchor_s"] == 150. and max(receipt["current_mode_direct_perturbation_max_difference"].values()) <= 1e-10, "Current coordinate reproduction fails")
    if "policy" in receipt:
        require(receipt["policy"]["zero_mean"] and receipt["policy"]["shrinkage_to_identity"] == .5 and receipt["policy"]["covariance_eigenvalue_bounds"] == [1., 16.], "Runtime prior policy differs")
        require(not receipt["RF_or_GPS_used_for_covariance"] and receipt["added_columns"] == 0, "Prior changed model dimensionality or used RF/GPS")
    return dict(case=record["case"], status="ready", pair_count=len(matching), history_checked=True)


def audit_inputs(configuration):
    roster_path, inventory_path = configuration["roster_path"], configuration["support_inventory_path"]
    require(sha(roster_path) == configuration["roster_sha256"], "RF roster hash differs")
    require(sha(inventory_path) == configuration["support_inventory_sha256"], "Age inventory hash differs")
    roster, inventory = read(roster_path), read(inventory_path)
    for key in ("previous_combined", "previous_audit", "previous_roster"):
        require(sha(roster[key + "_path"]) == roster[key + "_sha256"], "Previous authority changed: " + key)
    old, old_audit = read(roster["previous_combined_path"]), read(roster["previous_audit_path"])
    old_records = {r["case"]: r for r in read(roster["previous_roster_path"])["cases"]}
    require(old_audit["status"] == "passed" and old_audit["results_sha256"] == roster["previous_combined_sha256"], "Previous audit binding differs")
    old_rows = {r["case"]: r for r in old["rows"]}
    records, support = {r["case"]: r for r in roster["cases"]}, {r["case"]: r for r in inventory["rows"]}
    require(len(records) == len(roster["cases"]) == len(support) == len(inventory["rows"]) == 205 and set(records) == set(support) == set(old_rows), "Whole205 case sets differ")
    require(inventory["roster_sha256"] == sha(roster_path), "Inventory roster binding differs")
    require(inventory["covariance_source_sha256"] == sha(REPORT / configuration["covariance_module"]), "Inventory prior source differs")
    require(not inventory["RF_or_GPS_or_position_fit_used"] and not roster["geographic_truth_read"] and not roster["reranking_performed"], "Construction used forbidden evaluation inputs")
    ready = {c for c, r in support.items() if r["status"] == "ready" and r["pair_count"] >= 2}
    require(len(configuration["candidate_cases"]) == len(set(configuration["candidate_cases"])) and set(configuration["candidate_cases"]) == ready, "Prospective ready subset differs")
    require(configuration["age_policy_minimum_pairs"] == MINIMUMS, "Primary/exploratory rules differ")
    checks = []
    for case, record in records.items():
        previous = old_rows[case]
        for key, value in old_records[case].items():
            require(record[key] == value, "Original RF roster metadata differs: " + key)
        require(sha(record["input_path"]) == record["input_sha256"] == previous["input_sha256"], "RF input binding differs: " + case)
        require(digest(previous) == record["previous_row_sha256"], "Saved previous row differs: " + case)
        require(record["selected_A"] == previous["variants"]["A"]["selected_output"] and record["selected_B"] == previous["variants"]["A+B"]["selected_output"], "Immutable comparator differs")
        target = previous.get("target_family")
        require(record["target_family"] == target == support[case]["target_family"], "Frozen nomination differs")
        nomination = {k: previous[k] for k in ("family_ranking", "eligible_families", "target_family") if k in previous}
        require(record["saved_nomination_sha256"] == (digest(nomination) if target is not None else None), "Nomination digest differs")
        if target is not None:
            require(target == previous["eligible_families"][0], "Nomination was reranked")
        checks.append(audit_prior(record, support[case]))
    return records, support, dict(status="passed", recordings=205, ready=len(ready), primary_ready=sum(support[c]["pair_count"] >= 3 for c in ready),
        exploratory_ready=sum(support[c]["pair_count"] == 2 for c in ready), roster_sha256=sha(roster_path), support_inventory_sha256=sha(inventory_path),
        covariance_source_sha256=inventory["covariance_source_sha256"], no_position_fit=True, no_GPS_read=True, case_checks=checks)


def audit_results(protocol_path, results_path):
    protocol, results = read(protocol_path), read(results_path)
    configuration = protocol["evaluation"]
    for path, expected in protocol["source_sha256"].items():
        require(sha(path) == expected, "Frozen source changed: " + path)
    records, support, construction = audit_inputs(configuration)
    require(results["protocol_sha256"] == sha(protocol_path) and results["roster_sha256"] == configuration["roster_sha256"], "Result authority binding differs")
    require(results["workers_joined"] and results["available"] == 205 and len(results["rows"]) == 205 and {r["case"] for r in results["rows"]} == set(records), "Final joined205 ledger differs")
    spec = importlib.util.spec_from_file_location("independent_age_old_receipt_checks", OLD / "review/audit_receipts.py")
    old_checks = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old_checks)
    counts, policy_counts, statuses = Counter(), Counter(), Counter()
    for result in results["rows"]:
        case = result["case"]
        record = records[case]
        require(read(REPORT / "evaluation/cases" / case / "result.json") == result, "Per-case final receipt differs")
        for key in ("input_sha256", "previous_row_sha256", "target_family", "saved_nomination_sha256", "identities"):
            require(result[key] == record[key], "Per-case binding differs: " + key)
        require(result["protocol_sha256"] == sha(protocol_path), "Per-case protocol differs")
        require(result["immutable_comparators"] == dict(ALGO07=record["baseline"], A=record["selected_A"], B=record["selected_B"]), "Immutable comparison output differs")
        if result["new_model_attempt_started"]:
            require(case in configuration["candidate_cases"] and result.get("attempt_started_utc_ns", 0) > protocol["created_utc_ns"], "Unapproved or pre-seal attempt")
            counts["attempted_cases"] += 1
        receipt, endpoints = result.get("age_prior_receipt", {}), result.get("raw_endpoints", {})
        if receipt:
            for key in ("status", "pair_count", "history_sha256", "nominal_elements_sha256", "temporal_extent_sha256", "coefficient_covariance"):
                require(receipt.get(key) == support[case].get(key), "Runtime/frozen inventory differs: " + key)
            audit_prior(record, receipt)
        committed = result["status"] in ("qualified", "qualification_rejected")
        qualified = bool(committed and receipt.get("status") == "ready" and set(endpoints) == set(ARMS) and all(endpoints[a].get("qualified") for a in ARMS))
        require(result["candidate_qualified"] == qualified, "Paired qualification differs")
        for arm, endpoint in endpoints.items():
            require(arm in ARMS, "Unexpected RF arm")
            counts["raw_arm_cells"] += 1
            counts["complete_arm_cells"] += endpoint.get("status") == "complete"
            counts["qualified_arm_cells"] += bool(endpoint.get("qualified"))
            require(read(REPORT / "evaluation/cases" / case / ("age-" + arm + ".rf.json")) == endpoint, "Raw RF cell receipt differs")
            if endpoint.get("qualified"):
                old_checks.endpoint_checks(endpoint, result["baseline_replay"][arm], configuration["solver"])
        if set(endpoints) == set(ARMS) and all(endpoints[a].get("status") == "complete" for a in ARMS):
            a, b = [endpoints[arm] for arm in ARMS]
            require(a["native_inventory"]["native_ids_sha256"] == b["native_inventory"]["native_ids_sha256"] and a["native_inventory"]["fitted_owners_sha256"] == b["native_inventory"]["fitted_owners_sha256"], "Matched c-arm native observations differ")
            require(a["history"][0]["reference"] == b["history"][0]["reference"], "Matched c-arm phase starts differ")
        for label, minimum in MINIMUMS.items():
            adopted = bool(qualified and receipt.get("pair_count", 0) >= minimum)
            chosen = {arm: dict(source=label + "_age_matched_covariance", x=endpoints[arm]["x"], reference=endpoints[arm]["reference"], objective=endpoints[arm]["objective"], rms_hz=endpoints[arm]["rms_hz"], associated=record["baseline"][arm]["associated"]) for arm in ARMS} if adopted else record["selected_A"]
            require(result["policies"][label] == dict(accepted=adopted, minimum_pairs=minimum, selected_output=chosen), "Policy adoption/fallback differs: " + label)
            policy_counts[label] += adopted
        require(result["candidate_accepted"] == result["policies"]["Age3"]["accepted"] and result["exploratory_accepted"] == result["policies"]["Age2"]["accepted"] and result["selected_output"] == result["policies"]["Age3"]["selected_output"], "Top-level selection differs")
        statuses[result["status"]] += 1
    require(results["policy_accepted"] == dict(policy_counts) and results["status_counts"] == dict(statuses), "Aggregate counts differ")
    counts["disk_arm_cells"] = 0
    counts["orphan_arm_cells"] = 0
    counts["checkpoint_only_arm_cells"] = 0
    by_case = {r["case"]: r for r in results["rows"]}
    for folder in (REPORT / "evaluation/cases").iterdir():
        require(folder.name in records, "Unexpected case artifact")
        for arm in ARMS:
            cell = folder / ("age-" + arm + ".rf.json")
            checkpoint = folder / ("age-" + arm + ".checkpoint.json")
            if cell.exists() or checkpoint.exists():
                require(by_case[folder.name]["new_model_attempt_started"], "RF artifact without start marker")
            counts["disk_arm_cells"] += cell.exists()
            counts["orphan_arm_cells"] += cell.exists() and arm not in by_case[folder.name].get("raw_endpoints", {})
            counts["checkpoint_only_arm_cells"] += checkpoint.exists() and not cell.exists()
    return dict(status="passed", results_sha256=sha(results_path), protocol_sha256=sha(protocol_path), recordings=205,
        roster_sha256=configuration["roster_sha256"], support_inventory_sha256=configuration["support_inventory_sha256"],
        no_position_fit=True, no_GPS_read=True, workers_joined=True, policy_accepted=dict(policy_counts), status_counts=dict(statuses),
        cells=dict(counts), construction=construction, auditor_sha256=sha(__file__))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--protocol", type=Path)
    p.add_argument("--configuration", type=Path, default=REPORT / "evaluation/proposed_configuration.json")
    p.add_argument("--results", type=Path, default=REPORT / "evaluation/results.json")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if args.protocol:
        result = audit_results(args.protocol, args.results)
        destination = args.output or ROOT / "final_audit.json"
    else:
        _, _, result = audit_inputs(read(args.configuration))
        destination = args.output or ROOT / "inventory_audit.json"
    destination.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in result.items() if k not in ("construction", "case_checks")}, indent=2))
