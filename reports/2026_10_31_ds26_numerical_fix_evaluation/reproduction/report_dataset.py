"""Report a sealed full DS26 cached numerical replay; truth is reporting only."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
ARMS = ("c0", "fitted_c")


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_hash(path, expected):
    if sha(path) != expected.removeprefix("sha256:"):
        raise ValueError(f"Hash mismatch: {path}")


def hash_map(mapping, base):
    for name, expected in mapping.items():
        path = Path(name)
        check_hash(path if path.is_absolute() else base / path, expected)


def verify_study(study, expected_cases=159):
    """Fail closed before the caller is permitted to obtain geographic truth."""
    protocol = read(study / "dataset-protocol.json")
    source_manifest = Path(protocol["source_manifest"])
    check_hash(source_manifest, protocol["manifest_sha256"])
    members = [
        r
        for r in read(source_manifest)["cases"]
        if r["recording_format"] == "short_window_iq_recording"
    ]
    names = [r["case"] for r in members]
    if len(names) != expected_cases or len(set(names)) != len(names):
        raise ValueError("Incorrect full fast-scan denominator")
    if names != protocol["fast_cases"]:
        raise ValueError("Study roster differs from the frozen full fast-scan manifest")
    seal = read(study / "final-dataset-seal.json")
    if not seal.get("no_GPS_inference") or not seal.get("completed_before_reporting"):
        raise ValueError("Dataset must be sealed before reporting truth")
    check_hash(study / "source-freeze.json", seal["source_freeze_sha256"])
    freeze = read(study / "source-freeze.json")
    for field in ("source_hashes", "source_sha256", "files_sha256", "files"):
        if isinstance(freeze.get(field), dict):
            hash_map(freeze[field], study)
            break
    else:
        raise ValueError("Source freeze has no recognized file-hash dictionary")
    receipt_hashes = seal["receipt_sha256"]
    if set(receipt_hashes) != set(names):
        raise ValueError("Final seal does not cover every and only the full cohort")
    cases = []
    for member in members:
        case = member["case"]
        folder = study / "cases" / case
        check_hash(folder / "receipt.json", receipt_hashes[case])
        receipt = read(folder / "receipt.json")
        if receipt.get("case") != case:
            raise ValueError("Receipt belongs to another acquisition")
        outcome = None
        if receipt["state"] == "complete":
            inference = read(folder / "inference-seal.json")
            if not inference.get("no_GPS_inference"):
                raise ValueError("Missing inference separation declaration")
            hash_map(inference["source_hashes"], folder)
            hash_map(inference["output_hashes"], folder)
            required = {
                str(folder / name) for name in ("outcome.json", "decision.json", "protocol.json")
            }
            actual = {
                str(Path(p) if Path(p).is_absolute() else folder / p)
                for p in inference["output_hashes"]
            }
            if not required <= actual:
                raise ValueError("Inference seal omits endpoint or protocol artifacts")
            outcome = read(folder / "outcome.json")
            if not outcome.get("no_GPS_inference") or outcome.get("case") != case:
                raise ValueError("Outcome lacks matched inference provenance")
            decision = read(folder / "decision.json")
            if decision.get("selected"):
                proofs = decision["selected"].get("source_receipts")
                if not proofs:
                    raise ValueError("Selected scientific candidate lacks sealed proof artifacts")
                hash_map(proofs, folder)
        elif receipt["state"] not in ("unavailable", "replay_failed"):
            raise ValueError(f"Nonterminal receipt state: {receipt['state']}")
        cases.append((member, receipt, outcome))
    return protocol, cases


def reporting_truth():
    # This function is called only after every inference receipt has been sealed
    # and verified. The site was supplied by the user for reporting, not fitting.
    return (37.849061591561885, -122.48574968092912)


def distance_km(position, truth):
    lat, lon, tlat, tlon = map(math.radians, (*position, *truth))
    a = (
        math.sin((lat - tlat) / 2) ** 2
        + math.cos(lat) * math.cos(tlat) * math.sin((lon - tlon) / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1 - a)))


def published_arms(terminal):
    return (
        terminal["selected"]["arms"] if terminal.get("selected") else terminal["baseline"]["arms"]
    )


def published_owners(terminal, arm):
    if terminal.get("selected"):
        return terminal["selected"]["arms"][arm]["owners"]
    return terminal["source_support"][arm]["owners"]


def association_ids(arm, fallback_owners=None):
    if "associated_ids" in arm:
        result = set(arm["associated_ids"])
        if "owners" in arm and result != set(arm["owners"]):
            raise ValueError("Associated identities differ from the ownership proof")
        return result
    if fallback_owners is not None:
        return set(fallback_owners)
    gates = arm.get("gates", {}).get("tracks", []) + arm.get("linear_gates", [])
    if not gates or any("observation_ids" not in gate for gate in gates):
        raise ValueError("Missing explicit observation identities")
    return {oid for gate in gates for oid in gate["observation_ids"]}


def support_digest(ids, owners):
    return hashlib.sha256(
        json.dumps({"ids": sorted(ids), "owners": owners}, sort_keys=True).encode()
    ).hexdigest()


def observation_ids(source_folder, member, terminal):
    snapshot = source_folder / "candidate-v2/recovery/snapshot/descriptor.json"
    descriptor = read(snapshot)
    if descriptor["input_sha256"] != member["input"]["sha256"]:
        raise ValueError("Public observation export belongs to another input")
    if descriptor["terminal"] != terminal["baseline"]:
        raise ValueError("Public observation export embeds another original comparator")
    name = descriptor["case"] + "/observations.json"
    path = Path(descriptor["root"]) / name
    check_hash(path, descriptor["files"][name])
    ids = [r["observation_id"] for r in read(path)]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate public observation identities")
    return set(ids)


def build_case_rows(
    member, receipt, outcome, terminal, truth, all_ids=None, decision=None, unavailable_reason=None
):
    """Separate a raw scientific selection from the accepted additive update."""
    available = terminal is not None and terminal.get("state") == "complete"
    if not available:
        return [
            dict(
                case=member["case"],
                arm=arm,
                available=False,
                replay_state=receipt["state"],
                accepted_update=False,
                unavailable_reason=unavailable_reason or receipt.get("reason"),
                baseline_error_km=None,
                candidate_error_km=None,
                baseline_associated=None,
                candidate_associated=None,
                available_observations=None,
            )
            for arm in ARMS
        ]
    baseline_arms = published_arms(terminal)
    accepted = bool(outcome and outcome.get("accepted_update"))
    if accepted:
        if not (terminal.get("read_audit") or {}).get("verified"):
            raise ValueError(
                "Historically unverified production read audit cannot accept an update"
            )
        if not outcome.get("selected") or not decision or not decision.get("selected"):
            raise ValueError("Accepted update lacks a raw selected scientific candidate")
        if outcome["selected"] != decision["selected"]:
            raise ValueError("Accepted endpoint differs from the sealed worker selection")
    elif outcome and outcome.get("selected") != terminal.get("selected"):
        raise ValueError("Rejected update did not preserve the published ALGO03 endpoint")
    candidate_arms = (
        outcome["selected"]["arms"]
        if outcome and outcome.get("selected")
        else outcome["baseline"]["arms"]
        if outcome
        else baseline_arms
    )
    if outcome and outcome["baseline"] != terminal["baseline"]:
        raise ValueError("Replay replaced the original ALGO02 comparator")
    rows = []
    for arm in ARMS:
        old, new = baseline_arms[arm], candidate_arms[arm]
        old_owners = published_owners(terminal, arm)
        new_owners = new.get("owners", old_owners)
        if any(new_owners.get(oid) != owner for oid, owner in old_owners.items()):
            raise ValueError("Candidate loses or changes a current published ALGO03 owner")
        old_ids, new_ids = association_ids(old, old_owners), association_ids(new, new_owners)
        if all_ids is not None and not (old_ids | new_ids) <= all_ids:
            raise ValueError("Endpoint claims observations outside its public GLRT input")
        if not accepted and (old != new or old_ids != new_ids):
            raise ValueError("Fallback candidate differs from its published ALGO03 comparator")
        old_error, new_error = (
            distance_km(old["endpoint_latlon"], truth),
            distance_km(new["endpoint_latlon"], truth),
        )
        raw = (decision or {}).get("selected")
        raw_arm = raw["arms"][arm] if raw else None
        raw_owners = raw_arm.get("owners", {}) if raw_arm else {}
        stages = (outcome or {}).get("stages", [])
        endpoint_changed = not np.allclose(
            old["endpoint_latlon"], new["endpoint_latlon"], rtol=0, atol=1e-12
        )
        support_changed = old_ids != new_ids or old_owners != new_owners
        rows.append(
            dict(
                case=member["case"],
                arm=arm,
                available=True,
                replay_state=receipt["state"],
                accepted_update=accepted,
                endpoint_changed=endpoint_changed,
                associated_ID_set_changed=old_ids != new_ids,
                owner_map_changed=old_owners != new_owners,
                actual_published_change=endpoint_changed or support_changed,
                accepted_identical_cached_candidate=accepted
                and not (endpoint_changed or support_changed),
                acceptance_reason=(outcome or {}).get("reason", "replay_failed_ALGO03_fallback"),
                raw_worker_selected=bool(raw),
                raw_worker_decision=(decision or {}).get("decision"),
                raw_worker_associated=len(association_ids(raw_arm)) if raw_arm else None,
                raw_removed_or_changed_published_owners=sum(
                    raw_owners.get(oid) != owner for oid, owner in old_owners.items()
                )
                if raw_arm
                else None,
                original_ALGO03_decision=terminal.get("decision"),
                historical_read_guard_verified=bool(
                    (terminal.get("read_audit") or {}).get("verified")
                ),
                baseline_error_km=old_error,
                candidate_error_km=new_error,
                delta_error_km=new_error - old_error,
                baseline_associated=len(old_ids),
                candidate_associated=len(new_ids),
                added_associated=len(new_ids - old_ids),
                lost_associated=len(old_ids - new_ids),
                available_observations=len(all_ids) if all_ids is not None else None,
                baseline_frequency_RMS_hz=old.get("RMS_hz"),
                candidate_frequency_RMS_hz=new.get("RMS_hz"),
                baseline_frequency_objective=old.get("negative_twice_elbo"),
                candidate_frequency_objective=new.get("negative_twice_elbo"),
                frequency_objectives_comparable=not support_changed,
                baseline_support_sha256=support_digest(old_ids, old_owners),
                candidate_support_sha256=support_digest(new_ids, new_owners),
                baseline_latitude_deg=old["endpoint_latlon"][0],
                baseline_longitude_deg=old["endpoint_latlon"][1],
                candidate_latitude_deg=new["endpoint_latlon"][0],
                candidate_longitude_deg=new["endpoint_latlon"][1],
                baseline_total_seconds=terminal.get("total_seconds"),
                replay_wall_seconds=(outcome or {}).get("wall_seconds"),
                charged_cached_seconds=(outcome or {}).get("charged_cached_seconds"),
                reused_stage_count=sum(stage["reused"] for stage in stages),
                rerun_stage_count=sum(not stage["reused"] for stage in stages),
                charged_original_stage_seconds=sum(
                    stage.get("charged_original_seconds", 0) for stage in stages
                ),
                replay_budget_accounted_seconds=(decision or {}).get("seconds"),
                replay_original_budget_seconds=(decision or {}).get("maximum_seconds"),
                unavailable_reason=unavailable_reason,
            )
        )
    return rows


def stats(values):
    return (
        dict(
            count=len(values),
            mean_km=float(np.mean(values)),
            median_km=float(np.median(values)),
            p95_km=float(np.quantile(values, 0.95)),
            worst_km=float(np.max(values)),
        )
        if values
        else {"count": 0, "mean_km": None, "median_km": None, "p95_km": None, "worst_km": None}
    )


def work_accounting(decision, protocol=None, cached_stages=()):
    """Count the authoritative worker schedule, including unexecuted stages.

    Stage-cache receipts alone omit budget-exhausted stages and exceptions thrown
    before the replay adapter records its cache receipt. Worker decision.stages
    and decision.attempts are therefore the primary work-completion records.
    """
    attempts = (decision or {}).get("attempts", [])
    stages = (decision or {}).get("stages", [])
    attempt_status = Counter(a.get("status", "missing_status") for a in attempts)
    stage_status = Counter(s.get("status", "missing_status") for s in stages)
    scheduled = set((protocol or {}).get("completed_target_ids", []))
    attempted = {a["track_id"] for a in attempts}
    budget_targets = set()
    stage_details = []
    for stage in stages:
        if stage.get("status") in ("budget_exhausted", "failed"):
            stage_details.append(
                {
                    k: stage[k]
                    for k in ("name", "status", "returncode", "error", "budget_seconds", "seconds")
                    if k in stage
                }
            )
        if stage.get("status") == "budget_exhausted":
            parts = stage.get("name", "").split("-")
            if len(parts) >= 3 and parts[0] == "target" and parts[1].isdigit():
                index = int(parts[1])
                if index < len(attempts):
                    budget_targets.add(attempts[index]["track_id"])
    for attempt in attempts:
        if attempt.get("status") == "discovery_budget_exhausted":
            budget_targets.add(attempt["track_id"])
    unresolved = {"not_started", "discovery_budget_exhausted", "missing_status"}
    terminal = [
        a
        for a in attempts
        if a.get("status", "missing_status") not in unresolved
        and not a.get("status", "").endswith("_execution_failed")
    ]
    timeout_errors = [
        s
        for s in stages
        if s.get("status") == "failed"
        and any(
            word in s.get("error", "").lower()
            for word in ("timeoutexpired", "timed out", "time budget")
        )
    ]
    return dict(
        original_completed_target_schedule=len(scheduled),
        actual_attempts=len(attempts),
        original_scheduled_targets_not_attempted=len(scheduled - attempted),
        unexpected_new_target_ids=sorted(attempted - scheduled) if protocol is not None else [],
        attempt_status_counts=dict(attempt_status),
        decision_stage_status_counts=dict(stage_status),
        targets_with_completed_scientific_decision=len(terminal),
        targets_with_RF_inclusion_decision=sum(
            a.get("status") in ("RF_qualified", "RF_rejected") for a in attempts
        ),
        budget_limited_targets=len(budget_targets),
        budget_limited_target_points=sum(
            a.get("points", 0) for a in attempts if a["track_id"] in budget_targets
        ),
        discovery_budget_exhausted_targets=attempt_status["discovery_budget_exhausted"],
        budget_exhausted_stages=stage_status["budget_exhausted"],
        failed_stages=stage_status["failed"],
        explicit_timeout_error_stages=len(timeout_errors),
        decision_stage_count=len(stages),
        stage_cache_record_count=len(cached_stages),
        executed_stage_receipt_gap=max(
            0, len(stages) - stage_status["budget_exhausted"] - len(cached_stages)
        ),
        failure_or_budget_stages=stage_details,
        worker_failure=(decision or {}).get("failure"),
    )


def aggregate_work(records):
    result = {
        "cases_with_worker_decision": sum(r["has_worker_decision"] for r in records),
        "case_count": len(records),
    }
    for field in (
        "original_completed_target_schedule",
        "actual_attempts",
        "original_scheduled_targets_not_attempted",
        "targets_with_completed_scientific_decision",
        "targets_with_RF_inclusion_decision",
        "budget_limited_targets",
        "budget_limited_target_points",
        "discovery_budget_exhausted_targets",
        "budget_exhausted_stages",
        "failed_stages",
        "explicit_timeout_error_stages",
        "decision_stage_count",
        "stage_cache_record_count",
        "executed_stage_receipt_gap",
    ):
        result[field] = sum(r[field] for r in records)
    for field in ("attempt_status_counts", "decision_stage_status_counts"):
        counter = Counter()
        for record in records:
            counter.update(record[field])
        result[field] = dict(counter)
    result["budget_limited_cases"] = [
        r["case"] for r in records if r["budget_limited_targets"] or r["budget_exhausted_stages"]
    ]
    result["failed_stage_cases"] = [r["case"] for r in records if r["failed_stages"]]
    result["interpretation"] = (
        "All original scans remain in the cohort; worker attempts and stages distinguish completed "
        "scientific decisions from budget omissions and failures. A failed cache receipt does "
        "not remove a failed worker stage from these counts."
    )
    return result


def summarize(rows):
    summaries = {}
    for arm in ARMS:
        pairs = [r for r in rows if r["arm"] == arm and r["available"]]
        denominator = sum(r["available_observations"] for r in pairs)
        baseline_associated = sum(r["baseline_associated"] for r in pairs)
        candidate_associated = sum(r["candidate_associated"] for r in pairs)
        regressions = [
            dict(
                case=r["case"],
                baseline_error_km=r["baseline_error_km"],
                candidate_error_km=r["candidate_error_km"],
                delta_error_km=r["delta_error_km"],
                added_associated=r["added_associated"],
            )
            for r in pairs
            if r["delta_error_km"] > 1e-9
        ]
        summaries[arm] = dict(
            full_scan_denominator=sum(r["arm"] == arm for r in rows),
            paired_complete=len(pairs),
            baseline=stats([r["baseline_error_km"] for r in pairs]),
            candidate=stats([r["candidate_error_km"] for r in pairs]),
            verified_GLRT_observations=denominator,
            baseline_associated=baseline_associated,
            candidate_associated=candidate_associated,
            baseline_associated_percent=100 * baseline_associated / denominator
            if denominator
            else None,
            candidate_associated_percent=100 * candidate_associated / denominator
            if denominator
            else None,
            accepted_update_cases=sum(r["accepted_update"] for r in pairs),
            actually_changed_cases=sum(r["actual_published_change"] for r in pairs),
            endpoint_changed_cases=sum(r["endpoint_changed"] for r in pairs),
            associated_ID_set_changed_cases=sum(r["associated_ID_set_changed"] for r in pairs),
            accepted_identical_cached_candidates=sum(
                r["accepted_identical_cached_candidate"] for r in pairs
            ),
            raw_selected_cases=sum(r.get("raw_worker_selected", False) for r in pairs),
            regressions=sorted(regressions, key=lambda r: r["delta_error_km"], reverse=True),
            improvements=sum(r["delta_error_km"] < -1e-9 for r in pairs),
            unchanged=sum(abs(r["delta_error_km"]) <= 1e-9 for r in pairs),
        )
        summaries[arm]["frequency_fit_changes"] = {
            "exact_ID_and_owner_pairs": sum(r["frequency_objectives_comparable"] for r in pairs),
            "support_changed_not_comparable": sum(
                not r["frequency_objectives_comparable"] for r in pairs
            ),
        }
        for label in ("frequency_RMS_hz", "frequency_objective"):
            changes = [
                r[f"candidate_{label}"] - r[f"baseline_{label}"]
                for r in pairs
                if r["frequency_objectives_comparable"]
                and r[f"candidate_{label}"] is not None
                and r[f"baseline_{label}"] is not None
            ]
            summaries[arm]["frequency_fit_changes"][label] = {
                "paired_scans": len(changes),
                "mean_delta": float(np.mean(changes)) if changes else None,
            }
    return summaries


def verify_baseline_checkpoint(summary):
    for arm, expected in {
        "c0": (1.324560277020008, 0.9932431466984788, 3.562466683815054),
        "fitted_c": (1.3072234606062052, 1.0099691118803937, 3.5506537870301305),
    }.items():
        row = summary[arm]
        if (
            row["paired_complete"],
            row["verified_GLRT_observations"],
            row["baseline_associated"],
        ) != (148, 650404, 461708):
            raise ValueError(
                "Published ALGO03 baseline denominator or association checkpoint changed"
            )
        actual = tuple(row["baseline"][key] for key in ("mean_km", "median_km", "p95_km"))
        if not np.allclose(actual, expected, atol=1e-10, rtol=0):
            raise ValueError("Published ALGO03 position checkpoint changed")


def plot(rows, output):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    for kind in ("error-cdf", "paired-errors", "association-versus-accuracy"):
        fig, axes = plt.subplots(1, 2, figsize=(12, 5))
        for ax, arm in zip(axes, ARMS, strict=True):
            pairs = [r for r in rows if r["arm"] == arm and r["available"]]
            old = np.array([r["baseline_error_km"] for r in pairs])
            new = np.array([r["candidate_error_km"] for r in pairs])
            if kind == "error-cdf":
                for values, label in ((old, "Published ALGO03"), (new, "Accepted replay endpoint")):
                    ax.step(
                        np.sort(values),
                        np.arange(1, len(values) + 1) / len(values),
                        where="post",
                        label=label,
                    )
                ax.set(xlabel="Position error (km)", ylabel="Fraction of common qualified scans")
                ax.legend()
            elif kind == "paired-errors":
                accepted = np.array([r["accepted_update"] for r in pairs])
                ax.scatter(
                    old[~accepted], new[~accepted], s=15, color="#999999", label="ALGO03 fallback"
                )
                ax.scatter(
                    old[accepted], new[accepted], s=25, color="#2166ac", label="Accepted update"
                )
                limit = max(np.max(old), np.max(new)) * 1.05
                ax.plot([0, limit], [0, limit], color="black", lw=0.7)
                ax.set(xlabel="Published ALGO03 error (km)", ylabel="Accepted replay error (km)")
                ax.legend()
            else:
                ax.scatter(
                    [r["added_associated"] for r in pairs],
                    (new - old) * 1000,
                    s=22,
                    color="#2166ac",
                    alpha=0.7,
                )
                ax.axhline(0, color="black", lw=0.7)
                ax.set(
                    xlabel="Additional qualified observation identities",
                    ylabel="Position error change (m; negative improves)",
                )
            ax.set_title(f"{arm} · {len(pairs)} paired / 159 total")
            ax.grid(alpha=0.2)
        fig.suptitle("DS26 fast scans · Cached conditional numerical replay")
        fig.tight_layout()
        for extension in ("png", "pdf"):
            fig.savefig(output / f"{kind}.{extension}", dpi=160)
        plt.close(fig)


def write_draft(summary, output):
    lines = [
        "# Draft DS26 cached numerical replay comparison",
        "",
        "All 159 fast scans remain in the denominator. Published ALGO03 is compared with "
        "accepted additive research updates from the frozen completed target schedule. "
        "Nomination candidates, aliases, partitions, original GLRT data "
        "and causal banks are retained. "
        "This is a cached conditional replay; it does not measure a fresh catalogue search.",
        "",
        "| Arm | Paired scans | Associated points before and after | "
        "Mean error km before and after | "
        "Median error km before and after | P95 error km before and after |",
        "",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for arm, row in summary["arms"].items():
        old, new = row["baseline"], row["candidate"]
        lines.append(
            f"| {arm} | {row['paired_complete']} / 159 | "
            f"{row['baseline_associated']:,} → {row['candidate_associated']:,} | "
            f"{old['mean_km']:.6f} → {new['mean_km']:.6f} | "
            f"{old['median_km']:.6f} → {new['median_km']:.6f} | "
            f"{old['p95_km']:.6f} → {new['p95_km']:.6f} |"
        )
    work = summary["work_accounting"]
    lines += [
        "",
        f"Worker decisions record {work['actual_attempts']} target attempts from "
        f"{work['original_completed_target_schedule']} original completed targets. "
        f"{work['targets_with_completed_scientific_decision']} reached a completed scientific "
        f"decision; {work['budget_limited_targets']} were limited by discovery or stage budgets. "
        f"There were {work['budget_exhausted_stages']} unexecuted budget-exhausted stages and "
        f"{work['failed_stages']} failed stages. Newly valid fits can consume the retained "
        "budget before later original targets are reached. `work-accounting.json` preserves "
        "every worker attempt status and every failed or budget-limited stage.",
    ]
    lines += [
        "",
        "Association percentages use 650,404 hash-verified original GLRT observations from "
        "148 available scans. The other 11 scans retain explicit unavailable rows. "
        "A raw worker selection becomes an accepted endpoint only when it preserves every "
        "published ALGO03 owner in both c arms. Historical production read-guard failures remain "
        "fallbacks. Research inference seals do not substitute for a new production OS read guard.",
        "",
        "Reused stage times remain charged against the original search budgets. "
        "Replay wall time and cached charged time are reported separately. "
        "Frequency RMS and objective changes are descriptive fit metrics; they do not establish "
        "improved localization. Geographic truth enters only this report "
        "after all inference seals verify.",
        "",
        "![Position error CDF](error-cdf.png)",
        "",
        "![Paired position errors](paired-errors.png)",
        "",
        "![Association and accuracy changes](association-versus-accuracy.png)",
        "",
        "Every positive error change appears in `tail-regressions.csv`; every case and c arm "
        "appears in `per-case.csv`. `summary.json` records raw and accepted selections, "
        "failures, denominators and paired c ablations.",
    ]
    (output / "DRAFT.md").write_text("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "report-draft")
    args = parser.parse_args()
    protocol, verified = verify_study(args.study)
    # No scientific worker imports occur in this reporting process.
    truth = reporting_truth()
    source = Path(protocol["source_manifest"]).parents[1]
    inventory = {r["case"]: r for r in read(source / "candidate-final-inventory.json")["rows"]}
    rows = []
    work_records = []
    for member, receipt, outcome in verified:
        case = member["case"]
        old = source / "cases" / case
        original_receipt = read(old / "candidate-receipt.json")
        check_hash(old / "candidate-receipt.json", inventory[case]["candidate_receipt_sha256"])
        terminal_path = old / "candidate-v2/terminal.json"
        terminal = None
        if inventory[case].get("terminal_sha256"):
            check_hash(terminal_path, inventory[case]["terminal_sha256"])
            terminal = read(terminal_path)
        if outcome:
            check_hash(Path(outcome["baseline_terminal"]), outcome["baseline_sha256"])
            if Path(outcome["baseline_terminal"]) != terminal_path:
                raise ValueError("Replay used another published ALGO03 comparator")
        available = terminal is not None and terminal.get("state") == "complete"
        ids = observation_ids(old, member, terminal) if available else None
        decision = read(args.study / "cases" / case / "decision.json") if outcome else None
        case_protocol = read(args.study / "cases" / case / "protocol.json") if outcome else None
        work = work_accounting(decision, case_protocol, (outcome or {}).get("stages", []))
        work.update(
            case=case, replay_state=receipt["state"], has_worker_decision=decision is not None
        )
        if work["unexpected_new_target_ids"]:
            raise ValueError(
                "Replay worker attempted a target outside the frozen completed schedule"
            )
        work_records.append(work)
        baseline_receipt = read(old / "baseline-receipt.json")
        reason = (
            None
            if available
            else (
                "no_existing_public_GLRT_input"
                if member.get("input") is None
                else original_receipt.get("reason")
                or baseline_receipt.get("reason")
                or f"original_baseline_{baseline_receipt['state']}"
            )
        )
        case_rows = build_case_rows(
            member, receipt, outcome, terminal, truth, ids, decision, reason
        )
        for row in case_rows:
            row.update(
                {
                    key: work[key]
                    for key in (
                        "actual_attempts",
                        "original_completed_target_schedule",
                        "budget_limited_targets",
                        "targets_with_completed_scientific_decision",
                        "budget_exhausted_stages",
                        "failed_stages",
                        "executed_stage_receipt_gap",
                    )
                }
            )
        rows.extend(case_rows)
    arm_summary = summarize(rows)
    verify_baseline_checkpoint(arm_summary)
    by_case = {r["case"]: r for r in rows if r["arm"] == "c0"}
    c_ablation = {}
    lookup = {(r["case"], r["arm"]): r for r in rows}
    for method in ("baseline", "candidate"):
        paired = [
            (r, lookup[r["case"], "fitted_c"]) for r in rows if r["arm"] == "c0" and r["available"]
        ]
        c_ablation[method] = {
            "matched_complete_scans": len(paired),
            "mean_error_delta_fitted_minus_c0_km": float(
                np.mean(
                    [fit[f"{method}_error_km"] - zero[f"{method}_error_km"] for zero, fit in paired]
                )
            ),
            "exact_ID_and_owner_pairs": sum(
                zero[f"{method}_support_sha256"] == fit[f"{method}_support_sha256"]
                for zero, fit in paired
            ),
        }
        for label in ("frequency_RMS_hz", "frequency_objective"):
            values = [
                fit[f"{method}_{label}"] - zero[f"{method}_{label}"]
                for zero, fit in paired
                if zero[f"{method}_support_sha256"] == fit[f"{method}_support_sha256"]
                and fit[f"{method}_{label}"] is not None
                and zero[f"{method}_{label}"] is not None
            ]
            c_ablation[method][label] = dict(
                paired_scans=len(values), mean_delta=float(np.mean(values)) if values else None
            )
    summary = dict(
        schema="ds26-cached-numerical-replay-report/v1",
        full_scan_denominator=len(verified),
        arm_rows=len(rows),
        truth_reporting_only=list(truth),
        arms=arm_summary,
        unavailable_reasons=dict(
            Counter(r["unavailable_reason"] for r in by_case.values() if not r["available"])
        ),
        replay_states=dict(Counter(r["replay_state"] for r in by_case.values())),
        acceptance_reasons=dict(
            Counter(r.get("acceptance_reason") for r in by_case.values() if r["available"])
        ),
        historical_read_guard_unverified_cases=sum(
            r["available"] and not r.get("historical_read_guard_verified") for r in by_case.values()
        ),
        timing=dict(
            replay_wall_seconds_sum=sum(
                r.get("replay_wall_seconds") or 0 for r in by_case.values()
            ),
            cached_virtual_seconds_sum=sum(
                r.get("charged_cached_seconds") or 0 for r in by_case.values()
            ),
            original_reused_stage_seconds_sum=sum(
                r.get("charged_original_stage_seconds") or 0 for r in by_case.values()
            ),
            reused_stage_count=sum(r.get("reused_stage_count") or 0 for r in by_case.values()),
            rerun_stage_count=sum(r.get("rerun_stage_count") or 0 for r in by_case.values()),
            interpretation="Wall execution and original reused-stage budget charges are separate; "
            "these timings do not measure fresh catalogue inference.",
        ),
        c_ablation=c_ablation,
        work_accounting=aggregate_work(work_records),
        c_ablation_interpretation="Matched observations, candidates, priors and budgets; "
        "fit deltas and position accuracy reported separately. "
        "Objectives changing support are not compared.",
        scope="Complete original fast-scan denominator; "
        "conditional cached completed-target replay; "
        "no fresh catalogue search, production mutation or replacement production OS read guard",
        provenance=dict(
            final_dataset_seal_sha256=sha(args.study / "final-dataset-seal.json"),
            reporter_sha256=sha(Path(__file__)),
        ),
    )
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    (args.output / "work-accounting.json").write_text(
        json.dumps(
            {"aggregate": summary["work_accounting"], "cases": work_records},
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    fields = sorted({key for row in rows for key in row})
    with (args.output / "per-case.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        writer.writerows(rows)
    with (args.output / "tail-regressions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            [
                "arm",
                "case",
                "baseline_error_km",
                "candidate_error_km",
                "delta_error_km",
                "added_associated",
            ],
        )
        writer.writeheader()
        for arm in ARMS:
            writer.writerows(dict(arm=arm, **row) for row in arm_summary[arm]["regressions"])
    plot(rows, args.output)
    write_draft(summary, args.output)
    print(json.dumps({"output": str(args.output), "arms": arm_summary}, indent=2))


if __name__ == "__main__":
    main()
