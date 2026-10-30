"""Finite-cohort ALGO03 promotion rules, fixed before the qualification run.

Evaluation errors enter only this module, never an inference decision. A failed
recovery with a valid ALGO02 fallback is a complete candidate result; a missing
result must remain missing. These operational tolerances are not confidence
intervals and do not establish performance at another observing location.
"""

import math
from statistics import mean, median

CRITERIA_ID = "algo03-promotion-2026-10-30-v1"
SCOPE_AMENDMENT_ID = "algo03-fast-only-user-scope-2026-10-30-v1"
ARMS = ("c0", "fitted_c")
REQUIRED_DATASETS = ("DS23", "DS24", "DS26")
FAST_COHORT_COUNTS = {"DS23": 207, "DS24": 34, "DS26": 159}
MAXIMUM_JOB_SECONDS = 2400.0
MAXIMUM_RECOVERY_P95_SECONDS = 1200.0
TOTAL_P95_BASELINE_MULTIPLIER = 2.0
TOTAL_P95_ALLOWANCE_SECONDS = 60.0
ABSOLUTE_NONREGRESSION_KM = 0.05
RELATIVE_NONREGRESSION = 0.05
PROVENANCE_FLAGS = (
    "matched_c_inputs",
    "causal_only",
    "no_GPS_inference",
    "read_audit_verified",
    "frozen_release_verified",
)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _quantile(values, fraction):
    values = sorted(values)
    index = (len(values) - 1) * fraction
    lower = math.floor(index)
    upper = math.ceil(index)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def _summary(values):
    if not values:
        return dict(count=0, mean_km=None, median_km=None, p95_km=None, worst_km=None)
    return dict(
        count=len(values),
        mean_km=mean(values),
        median_km=median(values),
        p95_km=_quantile(values, 0.95),
        worst_km=max(values),
    )


def _tolerance(baseline):
    return max(ABSOLUTE_NONREGRESSION_KM, RELATIVE_NONREGRESSION * baseline)


def qualify(cohort, rows, *, fast_only=True):
    """Return a reproducible decision over an exact frozen cohort.

    ``cohort`` contains job_id, dataset and acquisition_mode (from acquisition
    provenance, not a compatibility label). ``rows`` contains those fields plus
    arm, baseline/candidate dictionaries and PROVENANCE_FLAGS. Each dictionary
    has state, error_km and total_seconds; the candidate also has added_seconds.
    Total candidate runtime includes the original ALGO02 processing. Frequency objectives may be included separately
    in caller reports; they never enter these accuracy gates.
    """
    failures = []
    expected = {}
    for job in cohort:
        identifier = job["job_id"]
        if identifier in expected:
            raise ValueError("Duplicate frozen cohort job")
        if job["acquisition_mode"] not in {"fast", "adaptive"}:
            raise ValueError("Acquisition mode requires authoritative fast/adaptive provenance")
        if fast_only and job["acquisition_mode"] != "fast":
            failures.append(f"{identifier}: outside user-amended fast-only scope")
        expected[identifier] = job
    if not expected:
        raise ValueError("Empty frozen cohort")
    if fast_only:
        counts = {
            dataset: sum(job["dataset"] == dataset for job in cohort)
            for dataset in FAST_COHORT_COUNTS
        }
        if counts != FAST_COHORT_COUNTS or len(cohort) != sum(FAST_COHORT_COUNTS.values()):
            failures.append("Frozen fast-only denominator must be DS23=207, DS24=34, DS26=159")
    actual = {}
    for row in rows:
        key = (row["job_id"], row["arm"])
        if key in actual:
            raise ValueError("Duplicate result arm")
        if key[0] not in expected or key[1] not in ARMS:
            raise ValueError("Result outside frozen cohort")
        job = expected[key[0]]
        if any(row[k] != job[k] for k in ("dataset", "acquisition_mode")):
            raise ValueError("Result provenance differs from frozen cohort")
        # Flags describe the endpoint that would be published. An audited v1
        # fallback may survive a failed recovery audit; recovery failure itself
        # remains in the caller's receipt. Unavailable inputs publish nothing.
        if row["candidate"].get("state") == "complete":
            for name in PROVENANCE_FLAGS:
                if row.get(name) is not True:
                    failures.append(f"{key[0]}/{key[1]}: {name} not verified")
        for model in ("baseline", "candidate"):
            result = row[model]
            if result.get("state") not in {"complete", "unavailable", "failed", "missing"}:
                raise ValueError("Unknown terminal state")
            if result["state"] == "complete" and not (
                _number(result.get("error_km")) and result["error_km"] >= 0
            ):
                failures.append(f"{key[0]}/{key[1]}: invalid {model} position error")
            runtime = result.get("total_seconds")
            if not _number(runtime) or runtime < 0:
                failures.append(f"{key[0]}/{key[1]}: missing {model} total runtime")
        if (
            _number(row["candidate"].get("total_seconds"))
            and row["candidate"]["total_seconds"] > MAXIMUM_JOB_SECONDS
        ):
            failures.append(f"{key[0]}/{key[1]}: candidate exceeds whole-job runtime budget")
        added = row["candidate"].get("added_seconds")
        if not _number(added) or added < 0:
            failures.append(f"{key[0]}/{key[1]}: missing candidate recovery runtime")
        elif (
            _number(row["baseline"].get("total_seconds"))
            and _number(row["candidate"].get("total_seconds"))
            and abs(row["baseline"]["total_seconds"] + added - row["candidate"]["total_seconds"])
            > 1e-6
        ):
            failures.append(f"{key[0]}/{key[1]}: candidate runtime excludes baseline processing")
        if row["baseline"]["state"] == "complete" and row["candidate"]["state"] != "complete":
            failures.append(f"{key[0]}/{key[1]}: lost baseline position coverage")
        actual[key] = row
    missing = [
        (identifier, arm)
        for identifier in expected
        for arm in ARMS
        if (identifier, arm) not in actual
    ]
    failures.extend(f"{identifier}/{arm}: missing result" for identifier, arm in missing)
    absent_datasets = sorted(set(REQUIRED_DATASETS) - {j["dataset"] for j in cohort})
    failures.extend(f"{dataset}: absent from frozen cohort" for dataset in absent_datasets)

    groups = {"all": set(expected)}
    for dimension in ("dataset", "acquisition_mode"):
        for value in sorted({job[dimension] for job in cohort}):
            groups[f"{dimension}:{value}"] = {
                identifier for identifier, job in expected.items() if job[dimension] == value
            }
    for dataset in sorted({job["dataset"] for job in cohort}):
        for mode in ("fast", "adaptive"):
            ids = {
                identifier
                for identifier, job in expected.items()
                if job["dataset"] == dataset and job["acquisition_mode"] == mode
            }
            if ids:
                groups[f"dataset:{dataset}/{mode}"] = ids

    summaries = {}
    for group, identifiers in groups.items():
        summaries[group] = {}
        for arm in ARMS:
            present = [actual[(i, arm)] for i in sorted(identifiers) if (i, arm) in actual]
            paired = [
                row
                for row in present
                if all(
                    row[model]["state"] == "complete" and _number(row[model].get("error_km"))
                    for model in ("baseline", "candidate")
                )
            ]
            baseline = _summary([r["baseline"]["error_km"] for r in paired])
            candidate = _summary([r["candidate"]["error_km"] for r in paired])
            summaries[group][arm] = dict(
                cohort_count=len(identifiers),
                present_count=len(present),
                baseline_complete=sum(r["baseline"]["state"] == "complete" for r in present),
                candidate_complete=sum(r["candidate"]["state"] == "complete" for r in present),
                baseline=baseline,
                candidate=candidate,
            )
            if not paired:
                failures.append(f"{group}/{arm}: no paired position evidence")
                continue
            # Report all summaries; apply the same non-regression margin to both
            # arms, every dataset/mode, and every tail statistic.
            for metric in ("mean_km", "median_km", "p95_km", "worst_km"):
                if candidate[metric] > baseline[metric] + _tolerance(baseline[metric]) + 1e-12:
                    failures.append(f"{group}/{arm}: material {metric} regression")
    primary = summaries["all"]["fitted_c"]
    if (
        primary["baseline"]["mean_km"] is None
        or primary["candidate"]["mean_km"] >= primary["baseline"]["mean_km"] - 1e-12
    ):
        failures.append("all/fitted_c: mean error does not improve")
    for dataset in REQUIRED_DATASETS:
        result = summaries.get(f"dataset:{dataset}", {}).get("fitted_c")
        if result and (
            result["baseline"]["mean_km"] is None
            or result["candidate"]["mean_km"] >= result["baseline"]["mean_km"] - 1e-12
        ):
            failures.append(f"dataset:{dataset}/fitted_c: mean error does not improve")
    # Each job runtime occurs in both arm rows; count one authoritative pair.
    baseline_runtimes, candidate_runtimes, recovery_runtimes = [], [], []
    for identifier in expected:
        pair = [actual.get((identifier, arm)) for arm in ARMS]
        if not all(pair):
            continue
        for model in ("baseline", "candidate"):
            values = [r[model].get("total_seconds") for r in pair]
            if values[0] != values[1]:
                failures.append(f"{identifier}: paired {model} runtime differs")
        if pair[0]["candidate"].get("added_seconds") != pair[1]["candidate"].get("added_seconds"):
            failures.append(f"{identifier}: paired recovery runtime differs")
        if all(
            _number(r[model].get("total_seconds"))
            for r in pair
            for model in ("baseline", "candidate")
        ):
            baseline_runtimes.append(pair[0]["baseline"]["total_seconds"])
            candidate_runtimes.append(pair[0]["candidate"]["total_seconds"])
        if _number(pair[0]["candidate"].get("added_seconds")):
            recovery_runtimes.append(pair[0]["candidate"]["added_seconds"])
    runtime = dict(
        baseline_seconds=sum(baseline_runtimes),
        candidate_seconds=sum(candidate_runtimes),
        baseline_p95_seconds=_quantile(baseline_runtimes, 0.95) if baseline_runtimes else None,
        candidate_p95_seconds=_quantile(candidate_runtimes, 0.95) if candidate_runtimes else None,
        recovery_p95_seconds=_quantile(recovery_runtimes, 0.95) if recovery_runtimes else None,
    )
    if (
        runtime["recovery_p95_seconds"] is None
        or runtime["recovery_p95_seconds"] > MAXIMUM_RECOVERY_P95_SECONDS
    ):
        failures.append("all: recovery runtime P95 exceeds 1200s")
    if (
        runtime["baseline_p95_seconds"] is None
        or runtime["candidate_p95_seconds"] is None
        or runtime["candidate_p95_seconds"]
        > TOTAL_P95_BASELINE_MULTIPLIER * runtime["baseline_p95_seconds"]
        + TOTAL_P95_ALLOWANCE_SECONDS
    ):
        failures.append("all: total runtime P95 exceeds 2x baseline P95 plus 60s")
    return dict(
        criteria_id=CRITERIA_ID,
        passed=not failures,
        failures=sorted(set(failures)),
        scope_amendment_id=SCOPE_AMENDMENT_ID if fast_only else None,
        cohort_count=len(expected),
        expected_arm_count=2 * len(expected),
        present_arm_count=len(actual),
        missing_arms=missing,
        summaries=summaries,
        runtime=runtime,
        scope="finite frozen same-site cohort; no cross-site accuracy claim",
    )
