"""Verify winner-transplant packets, attach truth, and render all intervention comparisons."""

import argparse
import gzip

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from . import complete_detector_roster as roster
from . import hard_pilots_eval as hard
from . import screening_figures
from . import winner_transplant_intervention as experiment
from . import winner_transplant_trial as trial
from .factor_cross import GATE, RANK, winner
from .full_held_scores import held_references
from .full_v5_check import _sha
from .margin_admission_results import fit, sealed, summaries
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .staggered_reconstruction_results import original_rows
from .support_cross_results import graph_support, resources

REPORT = trial.REPORT
read = whole_iq.read
STOCK, FIFTH = roster.FOUR, roster.FIVE


def audit_packet(before, capture, after, expected, mode):
    selected = {row["index"]: row["original_winner"] for row in expected}
    if len(selected) != len(expected):
        raise ValueError("one physical probe cannot be changed twice")
    before_meta, after_meta = (hard.support(doc) for doc in (before, after))
    if before_meta != after_meta:
        raise ValueError("transplant changed physical clock or recording metadata")
    fields = [doc["source"]["probes"] for doc in (before, capture, after)]
    for index, (old, archived, new) in enumerate(zip(*fields, strict=True)):
        if index not in selected:
            if new != old:
                raise ValueError("transplant modified an unselected packet")
            continue
        prior, donors, current = (probe["candidates"] for probe in (old, archived, new))
        if hard.metadata(old) != hard.metadata(new):
            raise ValueError("transplant modified immutable physical probe fields")
        if winner(donors) != selected[index] or winner(current) is None:
            raise ValueError("selected record is not the original admitted highest-margin winner")
        donor = donors[selected[index]]
        if current[winner(current)] != donor:
            raise ValueError("replacement winner did not exactly preserve the original fields")
        if (winner(prior) is not None) != (mode == "conflicts"):
            raise ValueError("changed packets no longer distinguish availability from conflicts")
        remaining = {row[RANK]: row for row in current if row[RANK] != donor[RANK]}
        for candidate in prior:
            if candidate[RANK] == donor[RANK]:
                continue
            gate = candidate[GATE] is True and (
                experiment.priority(candidate) <= experiment.priority(donor)
            )
            if remaining.pop(candidate[RANK]) != dict(candidate, **{GATE: gate}):
                raise ValueError("transplant modified a competing measurement")
        if remaining:
            raise ValueError("transplant introduced a non-donor measurement")


def verify(work, rows, plan, selections, authority):
    expected = {(p["id"], p["condition"]): p for p in plan["schedule"]}
    measured = {(r["id"], r["condition"]): r for r in rows}
    fixed_roster = {(ident, mode) for ident in trial.CASES for mode in trial.MODES}
    if (
        len(rows) != len(fixed_roster)
        or len(plan["schedule"]) != len(fixed_roster)
        or measured.keys() != fixed_roster
        or expected.keys() != fixed_roster
    ):
        raise ValueError("the schedule or its reported outcomes do not cover the fixed cohort")
    witnesses = []
    for ident in trial.CASES:
        case, request = whole_iq.binding(ident)
        docs, bindings = hard.resolve(ident, case)
        chosen, pairs, placebo_size = experiment.select(ident, docs)
        proof = selections[ident]
        if (
            bindings != proof["bindings"]
            or bindings != authority[ident]["sources"]
            or chosen != proof["selections"]
            or pairs != proof["matched_pairs"]
            or placebo_size != proof["placebo_eligible"]
        ):
            raise ValueError("the pre-inference native bodies or placebo pairs changed")
        stock = docs["four"]
        for mode in trial.MODES:
            result, planned = measured[ident, mode], expected[ident, mode]
            if any(result[k] != v for k, v in planned.items()):
                raise ValueError("worker terminal row differs from its prespecified input")
            validate_result(result["result"])
            directory = work / ident / mode
            stage = directory / "recording"
            actual = whole_iq.checked(stage / "native.json", result["native_sha256"])
            launched = result["terminal"] != "not-launched"
            request_path = whole_iq.checked(
                stage / "request.json", result["prepared_request_sha256"]
            )
            trial.verify_request(
                read(request_path), request, native_path=actual, native_sha256=_sha(actual)
            )
            audit_packet(stock, docs["capture"], read(actual), chosen[mode], mode)
            if launched:
                if read(directory / "attempt.json") != result:
                    raise ValueError("the publication differs from its actual service receipt")
                log = whole_iq.checked(directory / "service.log", result["log_sha256"])
                copy = REPORT / "logs" / f"{ident}-{mode}.log.gz"
                write(copy, gzip.compress(log.read_bytes(), mtime=0))
            resource = result.get("position_resources") or {}
            for edge in ("start", "end"):
                if resource and (
                    resource[edge]["cpus"] != [result["cpu"]]
                    or resource[edge]["nice"] != 10
                    or resource[edge]["memory.max"] != plan["memory_bytes"]
                    or resource[edge]["memory.swap.max"] != plan["swap_bytes"]
                    or resource[edge]["memory.swap.current"] != 0
                ):
                    raise ValueError("worker did not use prescribed CPU and memory limits")
            observed = result["result"]["metrics"].get("observations")
            if result["result"]["status"] == "ok" and not resource:
                raise ValueError("successful terminal solve must preserve a measured receipt")
            if observed is not None and observed != planned["positive_probes"]:
                raise ValueError("solver did not observe the intended winner support")
            witnesses.append(
                dict(
                    id=ident,
                    condition=mode,
                    launched=launched,
                    changed=len(chosen[mode]),
                    stock_positive=proof["stock_positive"],
                    resulting_positive=planned["positive_probes"],
                    preserved=len(stock["source"]["probes"]) - len(chosen[mode]),
                    native_sha256=result["native_sha256"],
                )
            )
    return witnesses


def scoring(rows, refs):
    scores = []
    for row in rows:
        ident, result = row["id"], row["result"]
        for arm in ARMS:
            report = fit(row, refs[ident], arm)
            base = refs[ident]["reference"]["baseline"][arm]["error_km"]
            current = report["error_km"]
            scores.append(
                dict(
                    report,
                    status="withheld"
                    if report["status"] == "ok" and not report["published"]
                    else report["status"],
                    cohort="challenge" if ident in hard.HARD else "known-control",
                    changed=row.get("changed", 0),
                    within_5pct_baseline=current is not None
                    and base is not None
                    and current <= 1.05 * base,
                    within_10pct_baseline=current is not None
                    and base is not None
                    and current <= 1.10 * base,
                    objective=result["metrics"].get(f"{arm}_frequency_score"),
                    **{
                        f"v5_{role}_error_km": refs[ident]["reference"][role][arm]["error_km"]
                        for role in ROLES
                    },
                )
            )
    return scores


def effects(scores):
    conditions = [(mode, trial.PREFIX + mode, STOCK) for mode in trial.MODES] + [
        ("matched_vs_placebo", trial.PREFIX + "matched_availability", trial.PREFIX + "placebo"),
    ]
    lookup = {(r["id"], r["method"], r["arm"]): r for r in scores}
    metrics = ("error_km", "conditional_rf_rms_hz", "observations", "tracks")
    rows = []
    for ident in trial.CASES:
        for arm in ARMS:
            for name, target, control in conditions:
                a, b = (lookup[ident, m, arm] for m in (target, control))
                diff = {}
                for field in metrics:
                    x, y = a[field], b[field]
                    diff["delta_" + field] = x - y if x is not None and y is not None else None
                points = [
                    [r["latitude"], r["longitude"]] if r["published"] else None for r in (a, b)
                ]
                diff["endpoint_shift_km"] = distance_km(*points)
                rows.append(dict(id=ident, arm=arm, cohort=a["cohort"], contrast=name, **diff))
    return rows


def report_summary(scores, deltas):
    groupings = {
        "all": set(trial.CASES),
        "challenge": set(hard.HARD),
        "known-control": set(hard.CONTROLS),
    }
    out = {}
    for group, ids in groupings.items():
        fits = [r for r in scores if r["id"] in ids]
        results = summaries(fits)
        for method, arms in results.items():
            for arm, data in arms.items():
                records = [r for r in fits if r["method"] == method and r["arm"] == arm]
                for cutoff in (5, 10):
                    field = f"within_{cutoff}pct_baseline"
                    data[field] = sum(row[field] for row in records)
        effects_by_arm = {}
        for arm in ARMS:
            effects_by_arm[arm] = {}
            for mode in {r["contrast"] for r in deltas}:
                subset = [
                    r
                    for r in deltas
                    if r["id"] in ids and r["contrast"] == mode and r["arm"] == arm
                ]
                fields = ("delta_error_km", "delta_conditional_rf_rms_hz", "delta_tracks")
                stats = {}
                for field in fields:
                    values = [r[field] for r in subset if r[field] is not None]
                    stats[field] = dict(distribution(values), decreased=sum(n < 0 for n in values))
                effects_by_arm[arm][mode] = stats
        out[group] = dict(scheduled=len(ids), results=results, paired=effects_by_arm)
    return out


def match_support(proofs):
    records = []
    for proof in proofs:
        chosen = proof["selections"]
        first, second = (chosen[k] for k in ("matched_availability", "placebo"))
        gaps = [abs(a["visit"] - b["visit"]) for a, b in zip(first, second, strict=True)]
        timing = distribution(gaps)
        records.append(
            dict(
                id=proof["id"],
                all_exclusive_availability=len(chosen["availability"]),
                eligible_placebo=proof["placebo_eligible"],
                matched_each=len(first),
                exclusive_conflicts=len(chosen["conflicts"]),
                median_visit_gap=timing["p50"],
                p95_visit_gap=timing["p95"],
                maximum_visit_gap=timing["max"],
            )
        )
    return records


def figures():
    names = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "summary.json",
        "scores.csv",
        "effects.csv",
        "resources.csv",
        "graph-support.csv",
        "matching.csv",
        "treatment-audit.csv",
        "capture-era-v5.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(trial.CASES), files={n: _sha(REPORT / n) for n in names}),
    )

    def series(key, method, label):
        return dict(
            key=key,
            value=method,
            file=names[0],
            label=label,
            native_field="paired_capture_sha256",
            match=[*roster.BINDINGS, "stock_native_sha256", "fifth_native_sha256"],
        )

    specs = []
    cases = (
        (
            "availability",
            "Restore missed winners on stock-negative probes",
            "availability",
            "All original-only additions",
            "Adds every capture-era winner absent from both fixed searches "
            "on stock-negative probes.",
        ),
        (
            "matched",
            "Compare equal-size gated-original additions",
            "matched_availability",
            "Matched original-only additions",
            "Equal-size placebo targets already had a gated physical match in fixed five.",
        ),
        (
            "conflicts",
            "Replace original-winner conflicts while preserving support",
            "conflicts",
            "Original common-positive winners",
            "Preserves the original stock positive-probe roster while changing selected winners.",
        ),
    )
    for suffix, title, mode, treatment, detail in cases:
        method = trial.PREFIX + mode
        baseline = trial.PREFIX + "placebo" if suffix == "matched" else FIFTH
        label = (
            "Equal-size gated-original placebo" if suffix == "matched" else "Complete fixed five"
        )
        specs.append(
            dict(
                id="winner-transplant-" + suffix,
                method=method,
                scope="roof",
                cases="sealed",
                seal="figure-lock.json",
                title=title,
                caption=(
                    "Six challenge recordings and two known controls. Privileged capture-era "
                    f"measurements enter fixed four before fresh position fits. {detail} "
                    "Service costs cover the stored factors through position only."
                ),
                provenance=list(names[1:]),
                series=[
                    series("one", method, treatment),
                    series("stock", STOCK, "Complete fixed four"),
                    series("one_native_factors", baseline, label),
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=specs))


def publish(work):
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    proof = sealed(REPORT, "prediction-lock.json", "selections.jsonl.gz")
    plan = read(REPORT / "plan.json")
    present, stock, fifth, _, bindings = trial.authority()
    if plan["sources"] != bindings or any(_sha(ROOT / n) != h for n, h in bindings.items()):
        raise ValueError("a locked scientific input or source changed")
    audit = verify(work, rows, plan, {r["id"]: r for r in proof}, present)
    controls = [
        dict(
            row,
            condition=condition,
            stock_native_sha256=stock[ident]["native_sha256"],
            fifth_native_sha256=fifth[ident]["native_sha256"],
        )
        for ident in trial.CASES
        for row, condition in ((stock[ident], "stock"), (fifth[ident], "fifth"))
    ]
    _, records = held_references(None, trial.CASES)
    refs = {r["id"]: r for r in records}
    scores = scoring(rows + controls, refs)
    deltas = effects(scores)
    csv_file(REPORT / "treatment-audit.csv", audit)
    csv_file(REPORT / "effects.csv", deltas)
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "resources.csv", resources([dict(supervisor_wall_s=None) | r for r in rows]))
    csv_file(REPORT / "graph-support.csv", graph_support(rows + controls))
    csv_file(REPORT / "matching.csv", match_support(proof))
    csv_file(REPORT / "capture-era-v5.csv", original_rows(refs, stock))
    save_json(REPORT / "summary.json", report_summary(scores, deltas))
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows + controls))
    figures()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        screening_figures.generate(args.plot, evidence=REPORT)
