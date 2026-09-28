#!/usr/bin/env python3
"""Audit frozen-model temporal-transfer results without rescoring geometry models."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from tools.rx_empirical_background import log_density

ARMS = ("D", "E", "S", "T")
FAMILIES = ("absolute", "within")
ROLES = ("reception", "held_frequency")
EVALUATIONS = (*ARMS, "T_swap", "T_reverse", *(f"{arm}_shift" for arm in ARMS))
COMPARISONS = (
    ("E", "D"),
    ("S", "D"),
    ("S", "E"),
    ("T", "D"),
    ("T", "S"),
    ("T", "T_swap"),
    ("T", "T_reverse"),
    *((arm, f"{arm}_shift") for arm in ARMS),
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_populations(document):
    records = {}
    all_ids = set()
    for lane in document["lanes"]:
        if lane["recording_split"] != "calibration":
            continue
        session = lane["lane"]["session_id"]
        record = records.setdefault(session, {role: {} for role in ROLES})
        period = float(lane["alias_period_hz"])
        for window in lane["windows"]:
            role = window["role"]
            if role not in ROLES:
                continue
            window_id = window["source_window_id"]
            if window_id in all_ids:
                raise ValueError("duplicate source window id")
            all_ids.add(window_id)
            frequencies = [
                [
                    float(item["canonical_rx0_hz"]) % period / period
                    for item in window["observed"][rx]
                ]
                for rx in ("rx0", "rx1")
            ]
            record[role][window_id] = {
                "counts": [len(values) for values in frequencies],
                "frequencies": frequencies,
                "rate_hz": window["sample_rate_hz"],
                "period_hz": period,
                "prediction_utc_ns": window["prediction_utc_ns"],
            }
    return records


def raw_reference(model, row):
    return log_density(model, row) - sum(row["counts"]) * math.log(row["period_hz"])


def logsumexp(values):
    maximum = max(values)
    return maximum + math.log(math.fsum(math.exp(value - maximum) for value in values))


def audit(results, document, cv_results, hashes):
    if results.get("schema") != "rx-geometry-temporal-transfer/v1":
        raise ValueError("unsupported result schema")
    if results.get("status") != "complete" or results.get("source_sha256") != hashes:
        raise ValueError("result is incomplete or source hashes differ")
    if cv_results.get("status") != "complete":
        raise ValueError("source CV result is incomplete")
    source = source_populations(document)
    if len(source) != 6:
        raise ValueError("expected six calibration recordings")
    expected_counts = {role: sum(len(record[role]) for record in source.values()) for role in ROLES}
    if expected_counts != {"reception": 1356, "held_frequency": 1363}:
        raise ValueError("unexpected source role populations")
    cv_folds = {fold["held_session"]: fold for fold in cv_results["folds"]}
    if sorted(cv_folds) != sorted(source):
        raise ValueError("CV and dataset recording memberships differ")
    if sorted(fold["held_session"] for fold in results["folds"]) != sorted(source):
        raise ValueError("transfer folds do not partition recordings")

    scores = {
        family: {role: {name: {} for name in EVALUATIONS} for role in ROLES}
        for family in FAMILIES
    }
    fold_receipts = []
    posterior_normalization_error = 0.0
    for fold in results["folds"]:
        session = fold["held_session"]
        frozen = cv_folds[session]
        baseline_ids = None
        for family in FAMILIES:
            evaluations = fold["families"][family]["evaluations"]
            if set(evaluations) != set(EVALUATIONS):
                raise ValueError("evaluation grid differs from frozen design")
            for name, evaluation in evaluations.items():
                exported = {role: [] for role in ROLES}
                sums = {
                    role: {"relative_log_score": 0.0, "reference_log_score": 0.0}
                    for role in ROLES
                }
                for lane in evaluation["lanes"]:
                    if len(lane["window_presence"]) != len(lane["windows"]):
                        raise ValueError("posterior/window export length mismatch")
                    if any(
                        not math.isfinite(value) or not 0 <= value <= 1
                        for value in lane["window_presence"]
                    ):
                        raise ValueError("invalid per-window presence probability")
                    for posterior_name in ("reception_posterior", "held_posterior"):
                        posterior = lane[posterior_name]
                        state = posterior["state_log_weights"]
                        nomination = posterior["nomination_log_weights_given_presence"]
                        errors = (
                            abs(logsumexp(state)),
                            abs(logsumexp(nomination)),
                            abs(posterior["presence_probability"] - (1.0 - math.exp(state[0]))),
                        )
                        posterior_normalization_error = max(
                            posterior_normalization_error, *errors
                        )
                        if max(errors) > 2e-12:
                            raise ValueError("posterior state probabilities do not normalize")
                    for window in lane["windows"]:
                        role = window["role"]
                        window_id = window["source_window_id"]
                        if window_id not in source[session][role]:
                            raise ValueError("export contains a foreign source window")
                        exported[role].append(window_id)
                        sums[role]["relative_log_score"] += window["relative_log_score"]
                        sums[role]["reference_log_score"] += window["reference_log_score"]
                        expected_reference = raw_reference(
                            frozen["background_model"], source[session][role][window_id]
                        )
                        if not math.isclose(
                            window["reference_log_score"], expected_reference, abs_tol=1e-9
                        ):
                            raise ValueError("raw joint reference score does not recompute")
                        if window["prediction_utc_ns"] != source[session][role][window_id][
                            "prediction_utc_ns"
                        ]:
                            raise ValueError("prediction timestamp differs from source")
                identity = {role: tuple(exported[role]) for role in ROLES}
                baseline_ids = identity if baseline_ids is None else baseline_ids
                if identity != baseline_ids:
                    raise ValueError("arm/control source IDs or order differ")
                for role in ROLES:
                    total = evaluation["roles"][role]
                    if len(exported[role]) != len(source[session][role]):
                        raise ValueError("role denominator differs from source")
                    if set(exported[role]) != set(source[session][role]):
                        raise ValueError("role source IDs differ from source")
                    if total["windows"] != len(exported[role]):
                        raise ValueError("role denominator differs from window export")
                    for metric in ("relative_log_score", "reference_log_score"):
                        if not math.isclose(total[metric], sums[role][metric], abs_tol=1e-8):
                            raise ValueError("window scores do not sum to role total")
                    expected_full = total["relative_log_score"] + total["reference_log_score"]
                    if not math.isclose(total["full_log_score"], expected_full, abs_tol=1e-8):
                        raise ValueError("full score is not reference plus relative")
                    for metric in (
                        "relative_log_score",
                        "reference_log_score",
                        "full_log_score",
                    ):
                        if not math.isclose(
                            total[f"{metric}_per_window"],
                            total[metric] / total["windows"],
                            abs_tol=1e-12,
                        ):
                            raise ValueError("per-window score arithmetic mismatch")
                    scores[family][role][name][session] = total[
                        "relative_log_score_per_window"
                    ]
                if name in ARMS:
                    expected = frozen["families"][family]["scores"][name]
                    reception = evaluation["roles"]["reception"]
                    for key in (
                        "windows",
                        "relative_log_score",
                        "reference_log_score",
                        "full_log_score",
                    ):
                        cv_key = "held_windows" if key == "windows" else key
                        cv_value = (
                            frozen["families"][family][cv_key]
                            if key in ("windows", "reference_log_score")
                            else expected[key]
                        )
                        tolerance = 0 if key == "windows" else 1e-8
                        if not math.isclose(reception[key], cv_value, abs_tol=tolerance):
                            raise ValueError("cellwise CV reception replay failed")
        for name in ("D", "D_shift"):
            if fold["families"]["absolute"]["evaluations"][name] != fold["families"][
                "within"
            ]["evaluations"][name]:
                raise ValueError("absolute and within D-family scores differ")
        fold_receipts.append(
            {
                "held_session": session,
                "reception_windows": len(source[session]["reception"]),
                "held_frequency_windows": len(source[session]["held_frequency"]),
            }
        )

    expected = {}
    for family in FAMILIES:
        for role in ROLES:
            for arm in ARMS:
                expected[f"{family}_{role}_{arm}-reference"] = scores[family][role][arm]
            for left, right in COMPARISONS:
                expected[f"{family}_{role}_{left}-{right}"] = {
                    session: scores[family][role][left][session]
                    - scores[family][role][right][session]
                    for session in source
                }
        for arm in ARMS:
            expected[f"{family}_{arm}_held-minus-reception"] = {
                session: scores[family]["held_frequency"][arm][session]
                - scores[family]["reception"][arm][session]
                for session in source
            }
        for left, right in COMPARISONS:
            expected[f"{family}_{left}-{right}_held-minus-reception"] = {
                session: (
                    scores[family]["held_frequency"][left][session]
                    - scores[family]["held_frequency"][right][session]
                    - scores[family]["reception"][left][session]
                    + scores[family]["reception"][right][session]
                )
                for session in source
            }
    if set(results["aggregate_equal_record"]) != set(expected):
        raise ValueError("aggregate grid differs from protocol")
    aggregates = {}
    for name, records in expected.items():
        exported = results["aggregate_equal_record"][name]
        mean = math.fsum(records.values()) / len(records)
        positive = sum(value > 0 for value in records.values())
        records_match = exported["records"].keys() == records.keys() and all(
            math.isclose(exported["records"][key], value, abs_tol=1e-12)
            for key, value in records.items()
        )
        if not records_match or not math.isclose(exported["mean"], mean, abs_tol=1e-12):
            raise ValueError("aggregate arithmetic mismatch")
        if exported["positive_records"] != positive:
            raise ValueError("aggregate sign count mismatch")
        aggregates[name] = {"mean": mean, "positive_records": positive}
    return {
        "schema": "rx-geometry-temporal-transfer-audit/v1",
        "status": "pass",
        "source_sha256": hashes,
        "population_windows": expected_counts,
        "posterior_normalization_max_abs_error": posterior_normalization_error,
        "folds": fold_receipts,
        "aggregate_equal_record": aggregates,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--cv-results", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    hashes = {"dataset": sha256(args.dataset), "cv_results": sha256(args.cv_results)}
    receipt = audit(
        json.loads(args.results.read_text()),
        json.loads(args.dataset.read_text()),
        json.loads(args.cv_results.read_text()),
        hashes,
    )
    receipt["results_sha256"] = sha256(args.results)
    with args.output.open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
