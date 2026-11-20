"""Verify the frozen quarter-miss fits and score the two cohorts independently."""

import argparse
import gzip

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution, validate_result
from . import one_lane_roster_results as baseline
from . import quarter_miss_trial as trial
from . import screening_figures, staggered_benchmark
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .staggered_reconstruction_results import original_rows
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
STOCK, HIT = trial.trial.fixed.FOUR, trial.trial.METHOD
QUARTER, PRIMARY = trial.METHOD, trial.PRIMARY
METHODS = (PRIMARY, HIT, QUARTER, STOCK)
LABELS = (
    "Alternating primary only",
    "Partner on hit",
    "Partner on hit plus quarter misses",
    "Both stock lanes",
)
FRESH_SCORE = "7bc8eeae59d208787ee8933aa1a7a4173164ac32d78b225c301442c681f5edba"
CONTRASTS = {
    "hit_minus_primary": (HIT, PRIMARY),
    "quarter_minus_hit": (QUARTER, HIT),
    "quarter_minus_primary": (QUARTER, PRIMARY),
    "quarter_minus_full": (QUARTER, STOCK),
}
read = whole_iq.read


def verify(work, plan, rows, evidence, groups):
    expected = {(r["id"], r["method"]): r for r in plan["schedule"]}
    observed = {(r["id"], r["method"]) for r in rows}
    cohort_by_id = {ident: label for label, ids in groups.items() for ident in ids}
    guard = {(ident, QUARTER) for ident in cohort_by_id} | {
        (ident, PRIMARY) for ident in groups["prospective2"]
    }
    if observed != guard or expected.keys() != guard or len(rows) != len(guard):
        raise ValueError("each frozen quarter-miss worker and fresh primary comparator is required")
    resources = []
    for r in rows:
        ident, method = r["id"], r["method"]
        if any(r[k] != v for k, v in expected[ident, method].items()):
            raise ValueError("post-fit row differs from the frozen request")
        verify_document = work / ident / r["condition"]
        if read(verify_document / "attempt.json") != r:
            raise ValueError("terminal prediction differs from the original worker receipt")
        whole_iq.checked(verify_document / "recording/native.json", r["native_sha256"])
        whole_iq.checked(verify_document / "recording/request.json", r["prepared_request_sha256"])
        log = whole_iq.checked(verify_document / "service.log", r["log_sha256"])
        write(
            REPORT / "logs" / f"{ident}-{method}.log.gz", gzip.compress(log.read_bytes(), mtime=0)
        )
        validate_result(r["result"])
        sample = r.get("position_resources") or {}
        if r["terminal"] == "success" and (
            not sample
            or r["result"]["metrics"].get("observations") != evidence[ident]["observations"][method]
        ):
            raise ValueError(
                "successful fit must retain its genuine resource and observation witness"
            )
        for stage in ("start", "end"):
            if sample and (
                sample[stage]["cpus"] != [r["cpu"]]
                or sample[stage]["nice"] != 10
                or sample[stage]["memory.max"] != plan["memory_bytes"]
                or sample[stage]["memory.swap.max"] != 0
                or sample[stage]["memory.swap.current"] != 0
            ):
                raise ValueError("measured worker did not use the frozen cgroup limits")
        resources.append(
            dict(
                id=ident,
                method=method,
                cohort=cohort_by_id[ident],
                cpu=r["cpu"],
                status=r["result"]["status"],
                terminal=r["terminal"],
                position_wall_s=sample.get("wall_s"),
                position_cpu_s=sample.get("cpu_s"),
                peak_bytes=sample.get("peak_bytes"),
                swap_bytes=sample.get("end", {}).get("memory.swap.current"),
                supervisor_wall_s=r.get("supervisor_wall_s"),
                detector_wall_s=None,
            )
        )
    return resources


def reference_sources(groups):
    original = trial.partner_holdout.REPORT
    authos, positions = [], []
    for root, seal_name, pin, authority, reference in (
        (original, "holdout-figure-lock.json", None, "paired-roof.json", "paired-v5.jsonl.gz"),
        (
            trial.fresh.REPORT,
            "score-lock.json",
            FRESH_SCORE,
            "roof-authority.json",
            "fresh-v5.jsonl.gz",
        ),
    ):
        receipt = sealed(root, seal_name, pin)
        get = trial.trial.fixed.member
        authos.extend(read(get(root, receipt, authority))["cases"])
        positions.extend(rows_from(get(root, receipt, reference)))
    specs, refs = {}, {}
    for label, ids in groups.items():
        specs[label], extra = staggered_benchmark.export_references(
            REPORT,
            label,
            ids,
            authos,
            positions,
        )
        _, old = held_references(None, [ident for ident in ids if ident not in extra])
        refs.update({row["id"]: row for row in old} | extra)
    for row in positions:
        if row["id"] not in refs:
            continue
        endpoints = refs[row["id"]]["reference"][row["method"]]
        for arm in ARMS:
            observed = row["result"].get("arms", {}).get(arm, {})
            endpoints[arm].update(
                latlon=observed.get("latlon"), rf_rms_hz=observed.get("rf_rms_hz")
            )
    return specs, refs


def matched_control(rows, groups, evidence, saved, hit, fresh):
    by_id = {(r["id"], r["method"]): r for r in rows}
    positions, stock_refs = [], {}
    for ident in groups["held14"] + groups["prospective2"]:
        is_fresh = ident in groups["prospective2"]
        controls = (
            (
                by_id[ident, PRIMARY],
                fresh[trial.fresh.METHOD][ident],
                fresh[trial.fresh.STOCK][ident],
            )
            if is_fresh
            else (saved[PRIMARY][ident], hit[ident], saved[STOCK][ident])
        )
        a, b, c = controls
        witness = evidence[ident]
        if (a["native_sha256"], b["native_sha256"], c["native_sha256"]) != (
            witness["one_lane_native_sha256"],
            witness["hit_native_sha256"],
            witness["stock_native"]["native_sha256"],
        ):
            raise ValueError("a paired baseline used a different stored detector input")
        stock_refs[ident] = c
        for method, row in zip(METHODS, (a, b, by_id[ident, QUARTER], c), strict=True):
            trial.trial.fixed.same_capture(c, row)
            positions.append(dict(row, method=method, stock_native_sha256=c["native_sha256"]))
    return positions, stock_refs


def scored(rows, groups, evidence, refs):
    data = baseline.comparisons(rows, refs)
    lookup = {(r["id"], r["method"], r["arm"]): r for r in data}
    cohorts = {i: group for group, ids in groups.items() for i in ids}
    for r in data:
        ident, method = r["id"], r["method"]
        r.update(
            cohort=cohorts[ident],
            scheduled_calls=evidence[ident]["calls"][method],
            observations=evidence[ident]["observations"][method],
        )
    effects, summary, comparisons = [], [], []
    for label, ids in groups.items():
        for arm in ARMS:
            subset = [r for r in data if r["cohort"] == label and r["arm"] == arm]
            for method in (*METHODS, *ROLES):
                result = trial.trial.fixed.summary_row(subset, ids, label, arm, method)
                selected = [r for r in subset if r["method"] == method]
                rf = distribution(
                    [r["rf_rms_hz"] for r in selected]
                    if selected
                    else [refs[i]["reference"][method][arm].get("rf_rms_hz") for i in ids]
                )
                summary.append(
                    dict(
                        result,
                        conditional_rf_n=rf["n"],
                        median_rf_rms_hz=rf["p50"],
                        at_most_5pct_above_stock=sum(
                            r["at_most_5pct_above_stock"] for r in selected
                        )
                        if selected
                        else None,
                        at_most_10pct_above_stock=sum(
                            r["at_most_10pct_above_stock"] for r in selected
                        )
                        if selected
                        else None,
                    )
                )
            for field in ("error_km", "rf_rms_hz", "frequency_score"):
                for contrast, (target, base) in CONTRASTS.items():
                    numbers = []
                    for ident in ids:
                        a, b = (lookup[ident, method, arm][field] for method in (target, base))
                        delta = a - b if a is not None and b is not None else None
                        effects.append(
                            dict(
                                id=ident,
                                cohort=label,
                                arm=arm,
                                metric=field,
                                contrast=contrast,
                                baseline=b,
                                candidate=a,
                                change=delta,
                            )
                        )
                        if delta is not None:
                            numbers.append(delta)
                    dist = distribution(numbers)
                    comparisons.append(
                        dict(
                            cohort=label,
                            arm=arm,
                            metric=field,
                            contrast=contrast,
                            scheduled=len(ids),
                            paired=dist["n"],
                            decreased=sum(n < 0 for n in numbers),
                            median=dist["p50"],
                            min=dist["min"],
                            max=dist["max"],
                        )
                    )
    return data, effects, summary, comparisons


def figures(rows, groups, roof):
    panels = []
    captions = {
        "held14": "Post-hoc robustness test on the previously evaluated fourteen recordings.",
        "prospective2": "Two new recordings selected before opening their geographic results.",
    }
    for label, ids in groups.items():
        name, lock = f"{label}-positions.jsonl.gz", f"{label}-figure-lock.json"
        pack(REPORT / name, [r for r in rows if r["id"] in ids])
        files = (
            "prediction-lock.json",
            "scores.csv",
            "effects.csv",
            "effects-summary.csv",
            "summary.csv",
            "resources.csv",
            "support.csv",
            *roof[label].values(),
        )
        save_json(
            REPORT / lock, dict(cases=ids, files={n: _sha(REPORT / n) for n in (name, *files)})
        )
        panels.append(
            dict(
                id=f"quarter-miss-{label}",
                method=QUARTER,
                scope="roof",
                cases="sealed",
                seal=lock,
                title="Partner on hits plus one quarter of primary misses"
                + (
                    " on fourteen earlier recordings"
                    if label == "held14"
                    else " on two new recordings"
                ),
                caption=(
                    f"{captions[label]} All four support sets derive from complete fixed-four "
                    "packets. Quarter-miss numerical times start from stored factors."
                ),
                provenance=list(files),
                roof_references=roof[label],
                series=[
                    dict(
                        key=key,
                        file=name,
                        label=description,
                        value=method,
                        native_field="paired_capture_sha256",
                        match=[*trial.trial.fixed.BINDINGS, "stock_native_sha256"],
                    )
                    for key, method, description in zip(
                        ("one_native_factors", "all_visits", "one", "stock"),
                        METHODS,
                        LABELS,
                        strict=True,
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=panels))


def publish(work):
    sealed(REPORT, "prediction-lock.json")
    plan, proof = (read(REPORT / n) for n in ("plan.json", "packet-audit.json"))
    lock, _, _, stock, _, _, _, hit, _, fresh = trial.authority()
    cohorts = {k: lock[k] for k in ("held14", "prospective2")}
    if (
        any(plan[k] != v for k, v in cohorts.items())
        or plan["policy_sha256"] != trial.POLICY_PIN
        or any(_sha(ROOT / n) != h for n, h in plan["files"].items())
    ):
        raise ValueError("frozen numeric design or dependency changed")
    raw = rows_from(REPORT / "predictions.jsonl.gz")
    resource = verify(work, plan, raw, proof, cohorts)
    rows, stock_refs = matched_control(raw, cohorts, proof, stock, hit, fresh)
    roof, refs = reference_sources(cohorts)
    scores, effects, summary, comparisons = scored(rows, cohorts, proof, refs)
    support = [
        dict(
            id=k,
            **{a: b for a, b in r.items() if isinstance(b, int)},
            **{f"{m}_calls": r["calls"][m] for m in METHODS},
            **{f"{m}_observations": r["observations"][m] for m in METHODS},
        )
        for k, r in sorted(proof.items())
    ]
    for file, values in (
        ("scores.csv", scores),
        ("effects.csv", effects),
        ("summary.csv", summary),
        ("effects-summary.csv", comparisons),
        ("support.csv", support),
        ("resources.csv", resource),
        ("capture-era-v5.csv", original_rows(refs, stock_refs)),
    ):
        csv_file(REPORT / file, values)
    figures(rows, cohorts, roof)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        screening_figures.generate(args.plot, evidence=REPORT)
