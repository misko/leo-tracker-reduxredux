"""Postfit independent no-retry, chronological coverage and RF decision audit.

No optimizer, RF refit, threshold change or geographic input is present. The
original receipt auditor remains frozen; this adds coverage-wave verification.
"""
import argparse
from collections import Counter
import json
import hashlib
import re
from pathlib import Path

import numpy as np

from audit_receipts import audit_case, read, require, sha


ROOT = Path(__file__).resolve().parent
REPORT = ROOT.parent
EVALUATION = REPORT / "evaluation"


def was_started(row, case_folder):
    """Conservative evidence of entry into a worker, independent of its score."""
    metadata = {"wall_seconds", "baseline_replay", "reconstruction",
                "numerical_trigger_diagnostics", "family_ranking", "prior_receipt", "traceback"}
    artifacts = Path(case_folder)
    return bool(row["status"] != "total_deadline_fallback"
                or metadata.intersection(row)
                or (artifacts.exists() and any(p.name != "result.json" for p in artifacts.iterdir())))


def scheduled_ids(records):
    groups = {}
    for record in records:
        groups.setdefault(record["dataset"], []).append(record["case"])
    for ids in groups.values():
        ids.sort()
    if not groups:
        return []
    return [groups[group][index]
            for index in range(max(map(len, groups.values())))
            for group in sorted(groups) if index < len(groups[group])]


def validate_packet(packet, path, expected_protocol, records):
    require(packet.get("workers_joined"), "Component workers have not joined")
    require(packet["protocol_sha256"] == expected_protocol, "Component protocol differs")
    by_case = {r["case"]:r for r in packet["rows"]}
    require(len(by_case) == len(packet["rows"]) == packet["available"], "Duplicate/count component mismatch")
    for case, row in by_case.items():
        require(case in records, "Component recording is outside original roster")
        require(row["protocol_sha256"] == expected_protocol, "Row protocol differs")
        require(row["input_sha256"] == records[case]["input_sha256"]
                and row["identities"] == records[case]["identities"]
                and row["dataset"] == records[case]["dataset"], "Row input/identity/dataset differs")
        receipt_path = path.parent / "cases" / case / "result.json"
        require(read(receipt_path) == row, "Aggregate differs from its per-case receipt")
    return by_case


def expected_next_cases(records, components):
    return {case for case in records if not any(case in rows and
            was_started(rows[case], path.parent/"cases"/case)
            for path, rows in components)}


def merge_authoritative(records, components):
    """Earliest started row wins; latest placeholder if no worker ever starts."""
    chosen, origins = {}, {}
    for path, rows in components:
        for case, row in rows.items():
            if case in chosen:
                old_path = origins[case]
                require(not was_started(chosen[case], old_path.parent/"cases"/case),
                        "A started recording was retried or replaced")
            chosen[case], origins[case] = row, path
    require(set(chosen) == set(records), "Combined coverage differs from full original roster")
    return chosen, origins


def causal_receipt_check(record, result):
    """Independently bind ready covariance to causal byte/availability records."""
    receipt = result.get("prior_receipt", {})
    if receipt.get("status") != "ready":
        return False
    from sgp4.api import Satrec
    scan = read(record["input_path"])["scan_receipt"]
    cutoff, origin = scan["cutoff_utc_ns"], scan["origin_utc_ns"]
    raw = read(receipt["history_path"])
    require(sha(receipt["history_path"]) == receipt["history_sha256"], "History bytes changed")
    nominal_digest = sha(receipt["nominal_elements_path"])
    require(nominal_digest == receipt["nominal_elements_sha256"] == raw["latest_elements_sha256"],
            "Nominal/history byte binding differs")
    require(raw["cutoff_utc_ns"] == cutoff <= origin == raw["origin_utc_ns"], "History timing differs")
    target = str(result["target_family"])
    nominal = read(receipt["nominal_elements_path"])[target]
    source_ledger = {(s["collected_utc_ns"], s["sha256"].removeprefix("sha256:")) for s in raw["sources"]}
    def element(lines):
        sat = Satrec.twoline2rv(*lines)
        epoch = int(round((sat.jdsatepoch-2440587.5+sat.jdsatepochF)*86400e9))
        digest = hashlib.sha256(("\n".join(lines)+"\n").encode()).hexdigest()
        require(int(sat.satnum) == int(target), "TLE bytes have another satellite number")
        return epoch, digest
    nominal_epoch, nominal_sha = element(nominal["lines"])
    nominal_provenance = nominal.get("provenance", nominal)
    require(nominal_provenance["collected_utc_ns"] == receipt["nominal_collected_utc_ns"]
            and nominal_provenance["snapshot_digest"].removeprefix("sha256:")
                == receipt["nominal_snapshot_sha256"], "Nominal provenance differs")
    require(nominal_sha == receipt["nominal_element_sha256"]
            and nominal_epoch == receipt["nominal_epoch_utc_ns"] <= cutoff, "Nominal element differs")
    require(receipt["nominal_snapshot_first_verified_collection_utc_ns"]
            <= receipt["nominal_collected_utc_ns"] <= cutoff, "Nominal availability differs")
    require((receipt["nominal_snapshot_first_verified_collection_utc_ns"],
             receipt["nominal_snapshot_sha256"]) in source_ledger,
            "Nominal same-snapshot availability witness differs")
    actual_records = {}
    for item in raw["past_versions"][target]:
        epoch, digest = element(item["lines"])
        require(abs(epoch-item["epoch"]) <= 2048, "History TLE-byte epoch differs")
        actual_records[(digest, item["epoch"], item["collected_utc_ns"], item["snapshot_sha256"])] = item
    epochs = []
    for selected in receipt["history_records"]:
        key = tuple(selected[k] for k in ("element_sha256", "epoch_utc_ns", "collected_utc_ns", "snapshot_sha256"))
        require(key in actual_records, "Selected history record not bound to its actual bytes")
        epoch, collected = selected["epoch_utc_ns"], selected["collected_utc_ns"]
        require(cutoff-int(72*3.6e12) <= epoch < nominal_epoch-1_000_000_000
                and cutoff-int(72*3.6e12) <= collected <= cutoff,
                "Selected history record violates causal age/availability")
        require((collected, selected["snapshot_sha256"].removeprefix("sha256:")) in source_ledger,
                "Historical snapshot availability witness differs")
        epochs.append(epoch)
    require(len(epochs) >= 3 and len(set(epochs)) == len(epochs)
            and all(a-b >= int(6*3.6e12) for a, b in zip(epochs, epochs[1:]))
            and (max(epochs)-min(epochs))/3.6e12 >= 12,
            "History thinning/span differs")
    coefficients = np.asarray([item["coefficients"] for item in receipt["historical_projection"]])
    require([item["epoch_utc_ns"] for item in receipt["historical_projection"]] == epochs,
            "Historical projection epochs differ")
    second = coefficients.T @ coefficients / len(coefficients)
    eigen, vectors = np.linalg.eigh(.5*np.eye(3)+.5*second)
    covariance = (vectors*np.clip(eigen, 1., 16.)) @ vectors.T
    require(np.allclose(covariance, receipt["coefficient_covariance"], atol=1e-10, rtol=0),
            "Covariance is not the declared causal shrunk second moment")
    require(receipt["added_columns"] == 0, "Causal intervention added an undeclared mode")
    return True


def audit(coverage_path, combined_path, destination):
    coverage = read(coverage_path)
    policy = coverage["coverage_completion"]
    original_path = Path(policy["original_protocol_path"])
    original = read(original_path)
    original_sha, coverage_sha = sha(original_path), sha(coverage_path)
    require(original_sha == policy["original_protocol_sha256"], "Original scientific execution seal changed")
    require(not coverage["scientific_policy_changed"] and not coverage["per_cell_budget_changed"]
            and not coverage["retried_actual_attempts_allowed"]
            and coverage["original_execution_window_unchanged"], "Coverage altered scientific policy")
    require(len(policy["allowed_waves"]) <= 2 and policy["workers"] == 16
            and 0 < policy["wave_seconds"] <= 1200, "Coverage plan exceeds declared ceiling")
    for source_packet in (original, coverage):
        for path, digest in source_packet["source_sha256"].items():
            require(sha(path) == digest, "Frozen source changed: " + path)
    roster_path = original["evaluation"]["roster_path"]
    roster_sha = sha(roster_path)
    require(roster_sha == original["evaluation"]["roster_sha256"], "Roster seal changed")
    roster = read(roster_path)
    records = {r["case"]:r for r in roster["cases"]}
    require(len(records) == len(roster["cases"]), "Duplicate original roster recording")
    combined = read(combined_path)
    require(combined["scientific_protocol_sha256"] == original_sha
            and combined["coverage_protocol_sha256"] == coverage_sha, "Combined protocol binding differs")
    require(combined.get("roster_sha256", combined.get("source_roster_sha256")) == roster_sha,
            "Combined roster binding differs")
    require(combined["available"] == len(records) and combined["workers_joined"], "Combined coverage/workers differ")
    require(combined["total_source_members"] == roster["total_source_members"]
            and combined["unavailable_source_members"] == roster["unavailable_source_members"],
            "Unavailable original source members differ")
    allowed_paths = [EVALUATION/"results.json"] + [EVALUATION/name/"results.json" for name in policy["allowed_waves"]]
    listed = combined["components"]
    paths = [Path(item["path"]).resolve() for item in listed]
    require(paths == [p.resolve() for p in allowed_paths[:len(paths)]] and paths,
            "Components are not a chronological original/completion prefix")
    components, component_checks, numerical_cells, orphan_cells = [], [], [], []
    interrupted_cells = []
    previous_end_ns = None
    for index, (path, receipt) in enumerate(zip(paths, listed)):
        require(sha(path) == receipt["sha256"], "Component hash differs")
        packet = read(path)
        expected_protocol = original_sha if index == 0 else coverage_sha
        rows = validate_packet(packet, path, expected_protocol, records)
        surfaced = {}
        for case, result in rows.items():
            for variant, label in [("A", "A"), ("A+B", "B")]:
                for arm, cell in result["variants"][variant].get("raw_endpoints", {}).items():
                    surfaced[(case, label, arm)] = cell
        terminal_keys = set()
        for cell_path in sorted((path.parent/"cases").glob("*/*.rf.json")):
            cell = read(cell_path)
            case = cell_path.parent.name
            require(case in rows, "Numerical cell is outside its component roster")
            key = (case, cell["model"], cell["arm"])
            terminal_keys.add(key)
            cell_receipt = dict(case=case, model=cell["model"], arm=cell["arm"],
                status=cell["status"], qualified=bool(cell.get("qualified")),
                path=str(cell_path), sha256=sha(cell_path))
            numerical_cells.append(cell_receipt)
            if key in surfaced:
                require(cell == surfaced[key], "Numerical cell differs from the surfaced pair receipt")
            else:
                orphan_cells.append(cell_receipt)
        interrupted = {}
        for artifact in sorted((path.parent/"cases").glob("*/*")):
            match = re.fullmatch(r"(A|B)-(c0|fitted_c)\.(rf|checkpoint)\.json(?:\.tmp)?", artifact.name)
            if not match or not artifact.is_file():
                continue
            key = (artifact.parent.name, match[1], match[2])
            if key in terminal_keys:
                continue
            require(key[0] in rows, "Interrupted cell is outside its component roster")
            interrupted.setdefault(key, []).append(artifact)
        for (case, model, arm), artifacts in interrupted.items():
            checkpoint = next((p for p in artifacts if p.name.endswith(".checkpoint.json")), None)
            last = read(checkpoint) if checkpoint is not None else {}
            interrupted_cells.append(dict(case=case, model=model, arm=arm,
                status="checkpoint_only_interruption" if checkpoint else "temporary_artifact_only_interruption",
                last_completed_phase_rounds=len(last.get("history", [])),
                elapsed_seconds_lower_bound=last.get("seconds"),
                artifacts=[dict(path=str(p), sha256=sha(p)) for p in artifacts]))
        started = read(path.parent/"execution_started.json")
        require(started["protocol_sha256"] == expected_protocol
                and started["cases"] == len(rows), "Execution receipt binding differs")
        require(not any(r["status"] == "running" for r in rows.values()), "Unfinished worker row remains")
        if previous_end_ns is not None:
            require(started["wall_utc_ns"] >= previous_end_ns, "Coverage waves overlap")
        previous_end_ns = started["wall_utc_ns"] + int(packet["wall_seconds"]*1e9)
        if index == 0:
            require(set(rows) == set(records), "Original ledger omits available recordings")
        else:
            require(coverage["created_utc_ns"] <= started["wall_utc_ns"], "Coverage policy was not prospective")
            plan = read(path.parent/"eligibility_plan.json")
            require(plan["coverage_protocol_sha256"] == coverage_sha
                    and plan["original_protocol_sha256"] == original_sha, "Eligibility protocol differs")
            require(plan["available_roster"] == len(records), "Eligibility roster count differs")
            expected = expected_next_cases(records, components)
            require(set(rows) == expected, "Coverage wave is not exactly the never-started roster")
            order = scheduled_ids([records[case] for case in expected])
            require(plan["selected_cases"] == order, "Coverage queue order differs")
            require(plan["prior_results"] == [dict(path=str(p), sha256=sha(p)) for p, _ in components],
                    "Eligibility prior hash/chronology differs")
            eligibility = {r["case"]:r for r in plan["eligibility"]}
            require(set(eligibility) == set(records), "Eligibility ledger is incomplete")
            require(all(item["eligible_never_started"] == (case in expected)
                        for case, item in eligibility.items()), "Eligibility decision differs")
        components.append((path, rows))
        component_checks.append(dict(path=str(path), sha256=sha(path), protocol_sha256=expected_protocol,
            recordings=len(rows), attempted=sum(was_started(r, path.parent/"cases"/case) for case, r in rows.items()),
            wall_seconds=packet["wall_seconds"], workers_joined=True))
    chosen, origins = merge_authoritative(records, components)
    combined_rows = {r["case"]:r for r in combined["rows"]}
    require(len(combined_rows) == len(combined["rows"]) == len(records), "Combined recordings duplicate or missing")
    require(combined_rows == chosen, "Combined source row differs from authoritative immutable component")
    provenance = {case:dict(results_path=str(path), results_sha256=sha(path)) for case, path in origins.items()}
    require(combined["provenance"] == provenance, "Combined per-recording provenance differs")
    remaining = sorted(case for case, row in chosen.items()
                       if not was_started(row, origins[case].parent/"cases"/case))
    require(combined["never_started_remaining"] == remaining, "Never-started count differs")
    require(combined["status_counts"] == dict(Counter(row["status"] for row in chosen.values())),
            "Combined status counts differ")
    checks = [audit_case(records[case], chosen[case], original["evaluation"]) for case in sorted(chosen)]
    independently_causal = sum(causal_receipt_check(records[case], chosen[case]) for case in sorted(chosen))
    replay_path = ROOT/"original_endpoint_replay_audit.json"
    replay = read(replay_path)
    require(replay["status"] == "passed" and replay["results_sha256"] == sha(paths[0])
            and replay["protocol_sha256"] == original_sha
            and replay["no_optimizer"] and replay["no_phase_refresh"] and replay["no_GPS_read"],
            "Bounded original endpoint replay binding differs")
    replayed_cases = [item["case"] for item in replay["checks"]]
    require(all(origins[case] == paths[0] and chosen[case] == components[0][1][case]
                for case in replayed_cases), "A replayed original recording was replaced")
    output = dict(status="passed", results_sha256=sha(combined_path),
        scientific_protocol_sha256=original_sha, coverage_protocol_sha256=coverage_sha,
        roster_sha256=roster_sha, auditor_sha256=sha(__file__),
        scientific_receipt_auditor_sha256=sha(ROOT/"audit_receipts.py"),
        no_position_fit=True, no_GPS_read=True, original_window_unchanged=True,
        no_actual_attempt_retried=True, exact_component_rows_preserved=True,
        recordings=len(checks), component_checks=component_checks,
        never_started_remaining=remaining,
        accepted={label:sum(r["accepted"][label] for r in checks) for label in ("A", "A+B", "A+B+C")},
        status_counts=dict(Counter(r["status"] for r in checks)),
        completed_endpoints=sum(r["completed_endpoints"] for r in checks),
        qualified_endpoints=sum(r["qualified_endpoints"] for r in checks),
        all_numerical_cell_receipts=len(numerical_cells),
        numerical_cell_status_counts=dict(Counter(r["status"] for r in numerical_cells)),
        orphan_unadopted_numerical_cell_count=len(orphan_cells),
        checkpoint_or_temporary_only_interrupted_cell_count=len(interrupted_cells),
        observed_attempted_arm_cell_lower_bound=len(numerical_cells)+len(interrupted_cells),
        interrupted_cells_without_terminal_RF_receipt=interrupted_cells,
        raw_cell_accounting_limit="An arm interrupted before its first durable per-arm marker "
            "cannot be counted exactly; terminal plus checkpoint/temporary cell evidence is a lower bound.",
        orphan_unadopted_numerical_cells=orphan_cells,
        numerical_cell_receipts=numerical_cells,
        geometry_guard_arms=sum(r["guard_arms"] for r in checks),
        causal_covariances_ready=sum(r["covariance_ready"] for r in checks),
        independently_verified_causal_covariances=independently_causal,
        bounded_endpoint_replay=dict(path=str(replay_path), sha256=sha(replay_path),
            original_results_sha256=sha(paths[0]), immutable_original_cases_in_combined=replayed_cases,
            optimizer_calls=0, new_replay_required=False),
        case_checks=checks)
    Path(destination).write_text(json.dumps(output, indent=2, allow_nan=False)+"\n")
    dense = {"case_checks", "numerical_cell_receipts", "orphan_unadopted_numerical_cells",
             "interrupted_cells_without_terminal_RF_receipt"}
    print(json.dumps({k:v for k,v in output.items() if k not in dense}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--coverage-protocol", type=Path, default=REPORT/"coverage_protocol.json")
    parser.add_argument("--combined-results", type=Path, default=EVALUATION/"combined_results.json")
    parser.add_argument("--output", type=Path, default=ROOT/"combined_audit.json")
    args = parser.parse_args()
    audit(args.coverage_protocol, args.combined_results, args.output)
