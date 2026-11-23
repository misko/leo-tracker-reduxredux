"""Score a frozen phase qualification rule on sealed, paired physical solver results."""

import argparse
import gzip
import json
from hashlib import sha256
from statistics import median

from accuracy_route_budget import DATA, read

ARMS = ("c0", "fitted_c")


def score_choice(qualified, errors, decisions):
    if qualified is not None and not isinstance(qualified, bool):
        raise ValueError("Expected the actual pre-fit Boolean qualification")
    if decisions["stock"] != "ok":
        raise ValueError("This challenge enrolled named fixes only")
    candidate_ok = decisions["cumulative"] == "ok"
    changes = (
        {arm: errors["cumulative"][arm] - errors["stock"][arm] for arm in ARMS}
        if candidate_ok
        else None
    )
    preserves = candidate_ok and max(changes.values()) <= 0
    allowed = candidate_ok and max(changes.values()) <= 0.250
    choice = "cumulative" if qualified else "stock"
    if qualified is None:
        outcome = "qualification unavailable"
    elif qualified == preserves:
        outcome = "correct choice"
    elif qualified:
        outcome = "selected regression"
    else:
        outcome = "missed improvement"
    return {
        "route": choice,
        "qualified": qualified,
        "both_errors_preserved": preserves,
        "within_250_m_both_arms": allowed,
        "outcome": outcome,
        "error_delta_km": changes,
    }


def compare(case, runs, errors):
    cumulative = runs["cumulative"]
    details = cumulative.get("route_details") or {}
    signed = details.get("signed", {})
    selected = signed.get("selection", {}).get("qualified")
    decisions = {mode: result["terminal"]["decision"] for mode, result in runs.items()}
    outcome = score_choice(selected, errors, decisions)
    elapsed = {mode: result["process"]["elapsed_s"] for mode, result in runs.items()}
    solve = (cumulative.get("worker") or {}).get("solve", {}).get("elapsed_s")
    mode = outcome["route"]
    return {
        "case": case,
        "prediction": outcome,
        "decisions": decisions,
        "horizontal_errors_km": errors,
        "signed_update_status": signed.get("status"),
        "saved_elapsed_s": elapsed,
        "selected_elapsed_s": elapsed[mode],
        "cumulative_solve_elapsed_s": solve,
        "full_solve_then_fallback_s": (
            elapsed[mode]
            if mode == "cumulative"
            else elapsed[mode] + solve
            if solve is not None
            else None
        ),
        "pre_evidence_elapsed_s": details.get("candidate_pre_evidence_clocks", {}).get(
            "elapsed_s"
        ),
        "qualify_elapsed_s": details.get("signed_qualify_clocks", {}).get("elapsed_s"),
    }


def development():
    rows = []
    for number in ("0155", "0160", "0316"):
        if number == "0160":
            partial = read("prospective-0160-partial-pair.json.gz")
            confirmed = read("prospective-0160-confirmation.json.gz")
            if not confirmed["reproduced_first_publication"]:
                raise ValueError("Confirmation must reproduce the first publication")
            runs = partial["runs"] | {"cumulative": confirmed["candidate"]}
            errors = {k: v["horizontal_error_km"] for k, v in partial["runs"].items()}
        else:
            record = read(f"prospective-{number}-solver.json.gz")
            runs = record["runs"]
            errors = record["scores"].get("horizontal_error_km") or {
                mode: {arm: v["horizontal_error_km"] for arm, v in values.items()}
                for mode, values in record["scores"].items()
            }
        rows.append(compare(f"DS30-{number}", runs, errors))
    return rows


def sealed(name, pin):
    data = (DATA / name).read_bytes()
    if sha256(data).hexdigest() != pin:
        raise ValueError(f"Receipt digest differs for {name}")
    return json.loads(gzip.decompress(data))


def india_control():
    source = sealed(
        "india-cumulative-transfer.json.gz",
        "dc731f2395e7a9b7b761a79e21a2fec91970d5d3e4a7eb11178bbfccef12af59",
    )
    rows = {}
    for offer, case in source["cases"].items():
        signed = source["runs"][offer]["cumulative"]["route_details"]["signed"]
        errors = {
            mode: {arm: result["arms"][arm]["error_km"] for arm in ARMS}
            for mode, result in case["scores"].items()
        }
        decisions = {mode: result["status"] for mode, result in case["scores"].items()}
        rows[offer] = {
            "choice": score_choice(signed["selection"]["qualified"], errors, decisions),
            "region_decision_correct": {
                mode: result["correct"] for mode, result in case["scores"].items()
            },
            "clearance_km": case["truth_clearance_km"],
        }
    return {
        "recording": source["case"],
        "detector_sha256": source["native_sha256"],
        "offers": rows,
    }


def totals(rows):
    stock = [row["saved_elapsed_s"]["stock"] for row in rows]
    choices = {
        "always_cumulative": [row["saved_elapsed_s"]["cumulative"] for row in rows],
        "phase_rule_free_decision": [row["selected_elapsed_s"] for row in rows],
        "phase_rule_full_solve_before_fallback": [
            row["full_solve_then_fallback_s"] for row in rows
        ],
    }
    return {
        name: None
        if any(t is None for t in times)
        else {
            "median_paired_ratio": median(
                t / s for t, s in zip(times, stock, strict=True)
            ),
            "summed_ratio": sum(times) / sum(stock),
            "saved_elapsed_s": sum(times),
            "named_elapsed_s": sum(stock),
        }
        for name, times in choices.items()
    }


def correction_path(transfer):
    from tools.pipeline_eval.scoring import distance_km

    reference = (
        DATA.parents[2] / "2026_11_21_ds30_full/reference-audit.json"
    ).read_bytes()
    if sha256(reference).hexdigest() != transfer["reference_sha256"]:
        raise ValueError("Survey reference does not match the sealed paired score")
    (site,) = (
        r["reference"]
        for r in json.loads(reference)["cases"]
        if r["dataset_label"] == transfer["case"]
        and r["authority_eligible"]
        and r["sealed_metadata_digests_verified"]
    )
    truth = site["latitude_deg"], site["longitude_deg"]
    details = transfer["runs"]["cumulative"]["route_details"]
    stages = {
        "initial": details["finish"],
        "repaired": details["repair"]["finish"],
        "signed": details["signed"]["finish"],
    }
    result = {
        name: {
            arm: {
                "horizontal_error_km": distance_km(truth, fit["latlon"]),
                "rf_rms_hz": fit["rf_rms_hz"],
                "conditional": fit["curved_points"],
                "predictive": fit["linear_points"],
            }
            for arm, fit in arms.items()
        }
        for name, arms in stages.items()
    }
    if any(
        result["signed"][arm]["horizontal_error_km"]
        != transfer["scores"]["cumulative"][arm]["horizontal_error_km"]
        for arm in ARMS
    ):
        raise ValueError("Final path position does not reproduce the paired score")
    return result


def study(receipt_name, receipt_pin):
    transfer = sealed(receipt_name, receipt_pin)
    if (
        transfer["case"] != "DS30-0402"
        or transfer["runs"]["stock"]["science"]["receipt"]["screened_nomination"][
            "winning_rank"
        ]
        != 1
    ):
        raise ValueError("Expected the first enrolled nonzero stock winner")
    runs = transfer["runs"]
    if any(
        r["process"]["exit_code"] != 0
        or r["terminal"]["native_sha256"].removeprefix("sha256:")
        != transfer["inputs"]["native_sha256"]
        for r in runs.values()
    ):
        raise ValueError("Both processes must finish from the same signed packet")
    errors = {
        mode: {arm: values[arm]["horizontal_error_km"] for arm in ARMS}
        for mode, values in transfer["scores"].items()
    }
    challenge = compare(transfer["case"], runs, errors)
    design = development()
    recorded = read("acquisition-throughput.json")["rows"]
    split = sorted(
        (r for r in recorded if r["stages"][0] > 0), key=lambda r: -r["stages"][1]
    )
    cohort = {r["case"] for r in [*design, challenge]}
    return {
        "protocol_commit": "7a617e230",
        "challenge_file": receipt_name,
        "challenge_sha256": receipt_pin,
        "development": design,
        "challenge": challenge,
        "challenge_fit_path": correction_path(transfer),
        "historical_stage_context": {
            "enrolled": len(recorded),
            "split_stage_count": len(split),
            "median_detection_to_terminal_s": median(r["stages"][1] for r in split),
            "descending_duration_ranks": {
                r["case"]: i
                for i, r in enumerate(split, start=1)
                if r["case"] in cohort
            },
        },
        "saved_time_scenarios": totals([*design, challenge]),
        "india_retrospective": india_control(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("receipt", help="Filename in the measurements directory")
    parser.add_argument(
        "sha256", help="Expected SHA-256 of the sealed challenge receipt"
    )
    args = parser.parse_args()
    print(json.dumps(study(args.receipt, args.sha256), indent=2, allow_nan=False))
