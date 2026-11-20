"""Verify and score the four matched capture-era versus fixed-four receiver inputs."""

import argparse
import gzip
from hashlib import sha256

from .. import figure_books, whole_iq
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, arm_outcome, distribution, thresholds, validate_result
from . import complete_detector_roster as fixed
from . import one_lane_capture_trial as trial
from . import one_lane_roster
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, summaries
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
CASES = trial.CASES
read = whole_iq.read
CAPTURE_BOTH, CAPTURE_ONE = ("one_lane_" + mode for mode in trial.MODES)
FOUR_BOTH, FOUR_ONE = fixed.FOUR, one_lane_roster.METHOD
CONTRASTS = (
    ("lane_capture", CAPTURE_ONE, CAPTURE_BOTH),
    ("lane_four", FOUR_ONE, FOUR_BOTH),
    ("detector_both", FOUR_BOTH, CAPTURE_BOTH),
    ("detector_one", FOUR_ONE, CAPTURE_ONE),
)
GROUPS = {
    "all": CASES,
    "difficult": trial.hard.HARD,
    "controls": trial.hard.CONTROLS,
}


def unique_index(rows, fields):
    owned = {}
    for row in rows:
        key = tuple(row[field] for field in fields)
        if key in owned:
            raise ValueError(f"duplicate measured cell {key}")
        owned[key] = row
    return owned


def member(folder, lock, name):
    return whole_iq.checked(folder / name, lock["files"][name])


def verify_measured(work, plan, predictions, audits):
    wanted = {(case, mode) for case in CASES for mode in trial.MODES}
    results = unique_index(predictions, ("id", "condition"))
    planned = unique_index(plan["schedule"], ("id", "condition"))
    if planned.keys() != wanted or results.keys() != wanted or audits.keys() != set(CASES):
        raise ValueError("the fresh study must retain all eight pairs and physical ledgers")
    for (ident, condition), outcome in results.items():
        row, audit = planned[ident, condition], audits[ident]
        if any(outcome[k] != value for k, value in row.items()):
            raise ValueError("the returned fit does not use its frozen request")
        if row["schedule_sha256"] != sha256(encoded(audit["selected"])).hexdigest():
            raise ValueError("the authenticated physical visit sequence changed")
        result = outcome["result"]
        validate_result(result)
        if set(result["arms"]) != set(ARMS):
            raise ValueError("the measured receiver must include both calibration arms")
        resources = outcome.get("position_resources")
        if outcome["terminal"] == "success" and resources is None:
            raise ValueError("a completed service must preserve its real resource measurement")
        if resources and any(
            resources[edge]["cpus"] != [row["cpu"]]
            or resources[edge]["nice"] != plan["nice"]
            or resources[edge]["memory.max"] != plan["memory_bytes"]
            or resources[edge]["memory.swap.max"] != plan["swap_bytes"]
            or resources[edge]["memory.swap.current"] != 0
            for edge in ("start", "end")
        ):
            raise ValueError("worker moved away from the pinned hard-cap specification")
        support = audit["probe_counts"]
        expected_count = support["selected"]["original"]
        if condition == "capture_both":
            expected_count += support["discarded"]["original"]
        observations = result["metrics"].get("observations")
        if observations is not None and observations != expected_count:
            raise ValueError("the real solver did not consume the intended original winners")
        if work is None:
            continue
        folder = work / ident / condition
        request = folder / "recording/request.json"
        native = whole_iq.checked(folder / "recording/native.json", row["native_sha256"])
        whole_iq.checked(request, row["prepared_request_sha256"])
        if read(folder / "attempt.json") != outcome:
            raise ValueError("the actual worker receipt changed")
        if condition == "capture_both":
            whole_iq.checked(native, row["paired_capture_sha256"])
        else:
            original = folder.with_name("capture_both") / "recording/native.json"
            whole_iq.checked(original, row["paired_capture_sha256"])
            one_lane_roster.audit_projection(read(original), read(native), audit["selected"])
        log = whole_iq.checked(folder / "service.log", outcome["log_sha256"])
        write(
            REPORT / "logs" / f"{ident}-{condition}.log.gz",
            gzip.compress(log.read_bytes(), mtime=0),
        )


def validate_controls(full, one, planned, packet, measured, audit):
    fixed.same_capture(full, one)
    fixed.same_capture(full, measured)
    if any(one[k] != v for k, v in planned.items()):
        raise ValueError("fixed-four one-lane result differs from its sealed request")
    if (
        one["stock_native_sha256"] != full["native_sha256"]
        or full["native_sha256"] != audit["bindings"]["four"]["native_sha256"]
        or packet["clock_authority"] != audit["rf_authority"]
        or packet["selected_visit_sha256"] != measured["schedule_sha256"]
        or packet["positive_probes"] != audit["probe_counts"]["selected"]["four"]
        or packet["stock_positive_probes"]
        != sum(part["four"] for part in audit["probe_counts"].values())
    ):
        raise ValueError("the fixed-four comparator does not use the same physical antenna mask")
    for row in (full, one):
        validate_result(row["result"])
        if set(row["result"]["arms"]) != set(ARMS):
            raise ValueError("the fixed-four comparator lacks one of its calibration arms")


def controls(plan, measured, audits):
    all_lock = fixed.REPORT / "all-figure-lock.json"
    all_files = read(all_lock)
    four = fixed.select(
        rows_from(member(fixed.REPORT, all_files, "all-positions.jsonl.gz")),
        FOUR_BOTH,
        all_files["cases"],
    )
    limits = ("receiver_files", "native_sources", "memory_bytes", "swap_bytes", "limit_s")
    projected = one_lane_roster.REPORT
    receipt = projected / "prediction-lock.json"
    lock = read(receipt)
    source = read(member(projected, lock, "plan.json"))
    packets = read(member(projected, lock, "packet-audit.json"))
    if source["groups"]["all"] != lock["cases"] or any(plan[key] != source[key] for key in limits):
        raise ValueError("the independent one-lane replay used a different compact worker")
    jobs = unique_index(source["jobs"], ("id",))
    alternatives = fixed.select(
        rows_from(member(projected, lock, "positions.jsonl.gz")), FOUR_ONE, lock["cases"]
    )
    capture = unique_index(measured, ("id", "method"))
    for ident in CASES:
        validate_controls(
            four[ident],
            alternatives[ident],
            jobs[ident,],
            packets[ident],
            capture[ident, CAPTURE_ONE],
            audits[ident],
        )
    joined = [r for ident in CASES for r in (four[ident], alternatives[ident])]
    origins = (all_lock, receipt, projected / "plan.json", projected / "packet-audit.json")
    return joined, {str(p.relative_to(ROOT)): _sha(p) for p in origins}


def paired(scores):
    lookup = unique_index(scores, ("id", "method", "arm"))
    fields = ("error_km", "conditional_rf_rms_hz", "observations", "tracks")
    for ident in CASES:
        for arm in ARMS:
            for name, variant, control in CONTRASTS:
                a, b = lookup[ident, variant, arm], lookup[ident, control, arm]
                common = a["published"] and b["published"]
                delta = {}
                for field in fields:
                    left, right = a[field], b[field]
                    delta["delta_" + field] = (
                        left - right if left is not None and right is not None else None
                    )
                yield dict(
                    id=ident,
                    arm=arm,
                    contrast=name,
                    variant=variant,
                    control=control,
                    variant_status=a["status"],
                    control_status=b["status"],
                    both_fix=common,
                    lost_fix=b["published"] and not a["published"],
                    rescued_fix=a["published"] and not b["published"],
                    within_10pct=common and a["error_km"] <= 1.10 * b["error_km"],
                    **delta,
                )


def per_case(rows, refs):
    for row in rows:
        ident = row["id"]
        stats = row.get("position_resources") or {}
        for arm in ARMS:
            record = fit(row, refs[ident], arm)
            endpoint = row["result"]["arms"][arm]
            record["status"], record["reason"] = arm_outcome(row["result"], endpoint)
            reference = refs[ident]["reference"]
            err, original = record["error_km"], reference["baseline"][arm]["error_km"]
            if record["status"] == "ok" and not record["published"]:
                record["status"] = "withheld"
            yield dict(
                record,
                cohort="difficult" if ident in GROUPS["difficult"] else "control",
                within_10pct_original=err is not None
                and original is not None
                and err <= 1.1 * original,
                position_cpu_s=stats.get("cpu_s"),
                position_wall_s=stats.get("wall_s"),
                peak_bytes=stats.get("peak_bytes"),
                conditional_frequency_score=row["result"]["metrics"].get(f"{arm}_frequency_score"),
                **{f"v5_{r}_error_km": reference[r][arm]["error_km"] for r in ROLES},
            )


def summary(scores, comparisons, refs):
    result = {}
    for group, ids in GROUPS.items():
        fitting = [row for row in scores if row["id"] in ids]
        delta = [row for row in comparisons if row["id"] in ids]
        geography = summaries(fitting)
        result[group] = dict(scheduled=len(ids), methods=geography, comparisons={}, original={})
        for method, per_arm in geography.items():
            for arm, value in per_arm.items():
                value["within_10pct_original"] = sum(
                    r["within_10pct_original"]
                    for r in fitting
                    if r["method"] == method and r["arm"] == arm
                )
        for contrast, _, _ in CONTRASTS:
            by_arm = {}
            for arm in ARMS:
                group_rows = [r for r in delta if (r["contrast"], r["arm"]) == (contrast, arm)]
                by_arm[arm] = {
                    k: sum(row[k] for row in group_rows)
                    for k in ("both_fix", "lost_fix", "rescued_fix", "within_10pct")
                } | {
                    k: distribution([row[k] for row in group_rows])
                    for k in ("delta_error_km", "delta_conditional_rf_rms_hz")
                }
            result[group]["comparisons"][contrast] = by_arm
        for role in ROLES:
            per_arm = {}
            for arm in ARMS:
                errors = [refs[ident]["reference"][role][arm]["error_km"] for ident in ids]
                per_arm[arm] = dict(error_km=distribution(errors), within_km=thresholds(errors))
            result[group]["original"][role] = per_arm
    return result


def figures(rows):
    series = [
        ("one", CAPTURE_ONE, "Original detector, one RX"),
        ("stock", CAPTURE_BOTH, "Original detector, both RX"),
        ("all_visits", FOUR_BOTH, "Fixed four, both RX"),
        ("one_native_factors", FOUR_ONE, "Fixed four, one RX"),
    ]
    common = [
        "prediction-lock.json",
        "comparison-sources.json",
        "scores.csv",
        "effects.csv",
        "pilot-support.csv",
        "original-v5.csv",
        "summary.json",
    ]
    charts = []
    groups = (
        ("all", "Detector and receiver-lane tradeoffs"),
        ("difficult", "Receiver-lane masking on six difficult recordings"),
        ("controls", "Receiver-lane masking on two controls"),
    )
    for group, title in groups:
        ids = GROUPS[group]
        positions, seal = f"positions-{group}.jsonl.gz", f"figure-{group}-lock.json"
        pack(REPORT / positions, [r for r in rows if r["id"] in ids])
        save_json(
            REPORT / seal,
            dict(cases=ids, files={name: _sha(REPORT / name) for name in (positions, *common)}),
        )
        charts.append(
            dict(
                id="one-lane-capture-" + group,
                method=CAPTURE_ONE,
                scope="roof",
                cases="sealed",
                title=title,
                seal=seal,
                provenance=common,
                caption=(
                    "Capture-era and fixed-four factors use the same per-RF RX alternation "
                    "and offer in actual phase-release solves. The four original v5 policies "
                    "use archived results. Masking stored factors measures position effects."
                ),
                series=[
                    dict(
                        key=key,
                        value=method,
                        label=label,
                        file=positions,
                        native_field="paired_capture_sha256",
                        match=list(fixed.BINDINGS),
                    )
                    for key, method, label in series
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))
    figure_books.generate(REPORT / "charts", ARMS, panel="screening", evidence=REPORT)


def publish(work):
    lock = read(REPORT / "prediction-lock.json")
    if tuple(lock["cases"]) != CASES:
        raise ValueError("original-only science differs from its named prospective roster")
    prediction = rows_from(member(REPORT, lock, "predictions.jsonl.gz"))
    plan = read(member(REPORT, lock, "plan.json"))
    audits = {r["id"]: r for r in rows_from(member(REPORT, lock, "schedule-audit.jsonl.gz"))}
    verify_measured(work, plan, prediction, audits)
    stock, dependencies = controls(plan, prediction, audits)
    save_json(REPORT / "comparison-sources.json", dependencies)
    rows = prediction + stock
    _, references = held_references(None, CASES)
    refs = {r["id"]: r for r in references}
    scores = list(per_case(rows, refs))
    comparisons = list(paired(scores))
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "effects.csv", comparisons)
    csv_file(
        REPORT / "original-v5.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                status=endpoint["status"],
                error_km=endpoint["error_km"],
                archived_rf_rms_hz=endpoint.get("rf_rms_hz"),
            )
            for ident in CASES
            for role in ROLES
            for arm in ARMS
            for endpoint in [refs[ident]["reference"][role][arm]]
        ],
    )
    csv_file(
        REPORT / "pilot-support.csv",
        [
            dict(id=ident, mask=part, **counts)
            for ident, proof in audits.items()
            for part, counts in proof["probe_counts"].items()
        ],
    )
    save_json(REPORT / "summary.json", summary(scores, comparisons, refs))
    figures(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=local_output, help="Optional original service-log audit")
    publish(parser.parse_args().work)
