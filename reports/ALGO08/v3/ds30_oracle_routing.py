"""Bound zero-cost whole-record routing from sealed original DS30 receipts."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from math import fsum
from pathlib import Path
from statistics import median

from .full_successor_score import ARMS, BUILDS, PINS, VERIFIED, paired_rows, roster


CAMPAIGN = Path("/srv/postgres-nvme/leo-ds30-evaluation-20261124")
PLAN = "sha256:9deecea6ce5237d01d277370f57b2666f3b84ab96bba72fe0b668c7701d0fc99"
EXPORT = "sha256:bceb23d2c1cb3fe0a4e26c4e377ef69fdd8899fd57b990a32c983491c1facf5b"
EXPORT_SEAL = "sha256:b1f0a8034f123b09f5253a043837774e924a6059d5a9fe3f1d69b3793c811557"
RELOCATION = "DS30-0452"
OVERLAY = "sha256:8428b6ac62cf3102e0018b0df9b3de498ef840fed6a5c8d10ea6bcba5bd397ed"
LIMIT = 12


def digest(data):
    return "sha256:" + sha256(data).hexdigest()


def checked(path, pin):
    data = path.read_bytes()
    if digest(data) != pin:
        raise ValueError(f"Sealed bytes changed at {path}")
    return data


def frozen_order(plan):
    planned = {row["case"]: row for row in plan["cases"]}
    smoke = plan["smoke"]
    if len(planned) != len(plan["cases"]) or len(smoke) != len(set(smoke)) or not set(smoke) <= planned.keys():
        raise ValueError("Original execution order is ambiguous")
    return [planned[case] for case in smoke] + [row for case, row in planned.items() if case not in smoke]


def included_prefix(plan, rows):
    prefix, pending = [], []
    for entry in frozen_order(plan)[:LIMIT]:
        case = entry["case"]
        group = rows[case]
        if len(group) != len(BUILDS) or {r["algorithm"] for r in group} != set(BUILDS):
            raise ValueError(f"Ambiguous frozen original pair for {case}")
        for row in group:
            fields = ("assigned_rank", "case_id", "order", "raw_identity_sha256", "manifest_raw_authority_sha256")
            if any(row[key] != entry[key] for key in fields) or row["first"] != entry["order"][0]:
                raise ValueError(f"Frozen original input or run order changed for {case}")
        measured = all(r["verified_pair"] and r["outcome"] in VERIFIED for r in group)
        if measured and not pending:
            prefix.append((entry, group))
        else:
            pending.append(dict(case=case, states={r["algorithm"]: r["admission_state"] for r in group}))
    return prefix, pending


def verified_rows(root):
    from .full_successor_score import REFERENCE

    plan = json.loads(checked(root/"plan.json", PLAN))
    seal = json.loads(checked(root/"rows-with-relocations-seal.json", EXPORT_SEAL))
    if seal["plan_sha256"] != PLAN or seal["combined_sha256"] != EXPORT:
        raise ValueError("The enrolment must use the frozen combined signed export")
    rows = {entry["case"]: [] for entry in frozen_order(plan)[:LIMIT]}
    for line in checked(root/"rows-with-relocations.jsonl", EXPORT).splitlines():
        row = json.loads(line)
        if row["case"] in rows:
            rows[row["case"]].append(row)
    prefix, pending = included_prefix(plan, rows)
    if not prefix or RELOCATION not in {entry["case"] for entry, _ in prefix}:
        raise ValueError("The independent verified relocation must be included")
    overlay_root = root/"relocation"/RELOCATION
    overlay = json.loads(checked(overlay_root/"overlay.json", OVERLAY))
    if (overlay["case"] != RELOCATION or overlay["plan_sha256"] != PLAN
            or overlay["proof_sha256"] != seal["proofs"][RELOCATION]
            or overlay["proof_path"] != f"relocation/{RELOCATION}/proof.json"):
        raise ValueError("The 0452 relocation does not bind the frozen campaign")
    checked(root/overlay["proof_path"], overlay["proof_sha256"])
    checked(overlay_root/"native-encoded-auth.json", overlay["encoded_auth_sha256"])

    verified, pairs = {}, []
    assigned = roster()
    for entry, group in prefix:
        case = entry["case"]
        source = overlay_root if case == RELOCATION else root/"cases"/case
        pair_body = (source/"pair.json").read_bytes()
        seal_pair = json.loads(pair_body)
        if (not seal_pair["verified_pair"] or not seal_pair["chronological"]
                or seal_pair["state"] != "observed_pair" or seal_pair["actual_order"] != entry["order"]
                or (case == RELOCATION and seal_pair != overlay["paired_scope"])):
            raise ValueError(f"Unsealed or out-of-order original pair for {case}")
        for row in group:
            role = row["algorithm"]
            pin = seal_pair["attempt_result_sha256"][role]
            attempt_path = root/row["attempt"]
            if (attempt_path.resolve(strict=True) != attempt_path or not attempt_path.is_relative_to(source/role)
                    or pin != row["attempt_result_sha256"] or row["generation"] != seal_pair["generation"]
                    or row["authority_sha256"] != seal_pair["authority_sha256"] or not row["acquisition_verified"]
                    or row["actual_order"] != seal_pair["actual_order"] or row["same_lease"] != seal_pair["same_lease"]
                    or (case == RELOCATION and overlay["paired_attempts"][role] != {"path": row["attempt"], "sha256": pin})):
                raise ValueError(f"Different selected attempt for {case}/{role}")
            attempt = json.loads(checked(attempt_path, pin))
            evidence = attempt["evidence"]
            arms = {name: dict(latlon=None, rf_rms_hz=None) | evidence["arms"][name] for name in ARMS}
            if (any(attempt[key] != row[key] for key in ("algorithm", "authority_sha256", "cpu_s", "elapsed_s", "generation", "outcome", "timing_scope"))
                    or evidence["raw_authority"] != row["raw_authority_sha256"] or arms != row["arms"]
                    or evidence["receipt"].get("terminal_sha256") != row["terminal_sha256"]
                    or any(attempt["process"][key] != row["child_"+key] for key in ("started_unix_ns", "finished_unix_ns", "cpu_s", "elapsed_s"))):
                raise ValueError(f"Export differs from the paid original attempt for {case}/{role}")
        checked_row, = paired_rows(group, {case: assigned[case]})
        pairs.append(checked_row)
        verified[case] = dict(pair_sha256=digest(pair_body), attempts=seal_pair["attempt_result_sha256"],
                              same_lease=seal_pair["same_lease"], ordered=entry["order"])
    return pairs, dict(plan=PLAN, export=EXPORT, export_seal=EXPORT_SEAL, relocation_overlay=OVERLAY,
                       relocated_proof=overlay["proof_sha256"], reference_sha256=REFERENCE, builds=PINS,
                       pairs=verified, pending=pending)


def support_mask(pairs, role, attribute, includes):
    return sum(1 << i for i, pair in enumerate(pairs) if includes(pair[role][attribute]))


def coverage(pairs, cutoffs):
    groups = {}
    for arm in ARMS:
        key = arm + "_error_km"
        thresholds = (sorted({r[key] for pair in pairs for r in pair if r[key] is not None})
                      if cutoffs is None else cutoffs)
        groups[arm] = [(None, *(support_mask(pairs, role, arm+"_fix", bool) for role in range(2)))]
        for limit in thresholds:
            def admitted(value):
                return value is not None and value <= limit

            groups[arm].append((limit, *(support_mask(pairs, role, key, admitted) for role in range(2))))
    return groups


def counts(comparison, route):
    threshold, installed, candidate = comparison
    actual = ((installed & ~route).bit_count() + (candidate & route).bit_count())
    return threshold, installed.bit_count(), actual


def meets(groups, route):
    return all(actual >= installed for group in groups.values() for _, installed, actual in (counts(row, route) for row in group))


def worst_deficit(groups, route):
    return max(0, max(installed-actual for group in groups.values() for _, installed, actual in (counts(row, route) for row in group)))


def clocks(pairs, route):
    metrics = {}
    for name, key in (("wall", "elapsed_s"), ("cpu", "cpu_s")):
        installed = [pair[0][key] for pair in pairs]
        selected = [pair[bool(route & (1 << i))][key] for i, pair in enumerate(pairs)]
        total = fsum(selected)
        paired_ratio = median(value/base for value, base in zip(selected, installed, strict=True))
        metrics[name] = dict(total_s=total, installed_s=fsum(installed), median_paired_ratio=paired_ratio,
                             sum_ratio=total/fsum(installed), summed_speedup=fsum(installed)/total,
                             median_paired_speedup=1/paired_ratio)
    return metrics


def optimize(pairs):
    if not 1 <= len(pairs) <= LIMIT:
        raise ValueError("Use only the nonempty first twelve sealed original pairs")
    finite, relaxed = coverage(pairs, None), coverage(pairs, (1., 2.))
    timing = [clocks(pairs, route) for route in range(1 << len(pairs))]

    def ratios(route):
        wall = timing[route]["wall"]
        return wall["sum_ratio"], wall["median_paired_ratio"]

    calibration = {arm: dict(finite_thresholds=len(finite[arm])-1) for arm in ARMS}

    def describe(route):
        witness = {}
        for arm, group in finite.items():
            errors = [counts(row, route) for row in group[1:]]
            negative = [(limit, named, assigned) for limit, named, assigned in errors if assigned < named]
            _, baseline_fixes, selected_fixes = counts(group[0], route)
            deficit = max((named-selected for _, named, selected in negative), default=0)
            witness[arm] = dict(installed_fixes=baseline_fixes, routed_fixes=selected_fixes,
                                finite_thresholds_below_installed=len(negative),
                                largest_deficit=deficit,
                                worst_first_threshold_km=next((limit for limit, named, selected in negative
                                                              if named-selected == deficit), None),
                                coverage=[dict(threshold_km=limit, installed=named, candidate=selected) for limit, named, selected
                                          in (counts(row, route) for row in relaxed[arm][1:])])
        return dict(mask=route, successor=[pair[0]["case"] for i, pair in enumerate(pairs) if route & (1 << i)],
                    calibrated_coverage=witness, **timing[route])

    def best(routes):
        total = min(routes, key=lambda route: (*ratios(route), route))
        middle = min(routes, key=lambda route: (*ratios(route)[::-1], route))
        both = min(routes, key=lambda route: (max(ratios(route)), *ratios(route), route))
        best_sum, best_median = ratios(total)[0], ratios(middle)[1]
        ties = dict(sum=sum(ratios(route)[0] == best_sum for route in routes),
                    median=sum(ratios(route)[1] == best_median for route in routes),
                    both=sum(ratios(route) == (best_sum, best_median) for route in routes))
        return dict(eligible=len(routes), minimum_sum=describe(total), minimum_median=describe(middle), joint=describe(both),
                    same_canonical_optima=total == middle, common_optimum=ties["both"] > 0, optimal_route_counts=ties)

    n = len(timing)
    return dict(records=len(pairs), routes=n, thresholds=calibration,
                installed=describe(0), all_successor=describe(n-1),
                strict=best([route for route in range(n) if meets(finite, route)]),
                relaxed=best([route for route in range(n) if meets(relaxed, route)]),
                unconstrained=best(list(range(n))),
                routes_for_figure=[[worst_deficit(finite, route), time["wall"]["summed_speedup"]]
                                   for route, time in enumerate(timing)])


def render_figure(result, output):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import MultipleLocator, StrMethodFormatter

    points = result["routes_for_figure"]
    deficits = range(1+max(count for count, _ in points))
    figure = Figure(figsize=(8.4, 4.6), dpi=160, layout="constrained")
    ax = figure.subplots()
    jittered = [count + ((index*73 % 257)/256-.5)*.25 for index, (count, _) in enumerate(points)]
    ax.scatter(jittered, [speed for _, speed in points], s=8, color="#6f7d87", alpha=.19, linewidths=0,
               label=f"{len(points):,} hypothetical routes", zorder=2)
    ax.step(deficits, [max(speed for count, speed in points if count <= allowed) for allowed in deficits],
            where="post", linewidth=1.5, color="#176084", label="Fastest within each deficit budget", zorder=3)
    ax.axhline(2, color="#746250", linewidth=1, linestyle="--", zorder=1)
    ax.text(.99, 2.015, "2× summed target", transform=ax.get_yaxis_transform(), ha="right", fontsize=9, color="#614c37")
    landmarks = ((result["installed"], "All installed · ", (14, -2), "left", "#30343a"),
                 (result["strict"]["minimum_sum"], "Fastest strict route\n", (14, 19), "left", "#176084"),
                 (result["all_successor"], "All candidate · ", (-14, 20), "right", "#af451d"))
    for route, label, offset, alignment, color in landmarks:
        count, speed = points[route["mask"]]
        ax.scatter([count], [speed], color=color, edgecolor="white", linewidth=.8, s=58, zorder=4)
        ax.annotate(f"{label}{speed:.3f}×", (count, speed), xytext=offset, textcoords="offset points",
                    ha=alignment, va="center", color=color, fontsize=9, fontweight="bold", zorder=5)
    ax.set(title=f"DS30 routing ceiling · {result['records']} sealed original pairs",
           xlabel="Largest drop in cumulative fix count at any error threshold, either calibration arm",
           ylabel="Summed elapsed speedup vs installed ALGO08v3", xticks=list(deficits),
           xlim=(-.26, deficits[-1]+.29), ylim=(.91, 2.10))
    ax.yaxis.set_major_locator(MultipleLocator(.2))
    ax.yaxis.set_major_formatter(StrMethodFormatter("{x:.1f}×"))
    ax.grid(color="#e1e5e8", linewidth=.7)
    ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(loc="upper left", bbox_to_anchor=(0, .89), frameon=False, fontsize=9)
    FigureCanvasAgg(figure).print_png(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    args = parser.parse_args()
    pairs, source = verified_rows(args.campaign)
    compact = ("case", "outcome", "elapsed_s", "cpu_s", "timing_scope", "c0_fix", "c0_error_km", "fitted_c_fix", "fitted_c_error_km")
    outcomes = {role: dict(Counter(pair[i]["outcome"] for pair in pairs)) for i, role in enumerate(BUILDS)}
    print(json.dumps(dict(source=source, outcomes=outcomes, result=optimize(pairs),
                          measurements=[{row["algorithm"]: {key: row[key] for key in compact} for row in pair} for pair in pairs]),
                     indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
