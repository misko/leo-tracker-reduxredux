"""Compare one physical antenna per visit with the three complete reference receivers."""

import csv

from .. import whole_iq
from ..__main__ import save_json
from ..scoring import ARMS, ROLES, arm_outcome, distance_km
from . import complete_detector_roster as fixed
from . import receiver_budget, receiver_budget_figure
from . import staggered_benchmark as earlier
from .full_held_scores import held_references
from .full_v5_check import _sha
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

BASE = fixed.SCREEN / "pilot-influence"
REPORT, PROJECTED, DIRECT = (
    BASE / s for s in ("one-lane-benchmark", "one-lane-roster", "one-lane-whole")
)
PARENT = "536d9a1a158fad6abe611e6c3401f041104cfb68d76da32e60acbd74a8180159"
PROJECTION_PLAN = "686727acdfd0c9b7cd0c341005e885bdd291c7f54d465efa047764130d47cc18"
RAW_PLAN = "8df7d34014e879603367fa7e36ab562276a16394f6e8e01fea459bd29d1ad23b"
ONE = "one_physical_lane"
METHODS = (*earlier.METHODS, ONE)
LABELS = {
    fixed.FOUR: "Four on both antennas",
    fixed.FIVE: "Five on both antennas",
    earlier.MIXED: "Alternating extra search",
    ONE: "One antenna per visit",
}
PANELS = {
    "all": (
        "Processing one antenna per visit on twenty-two roof recordings",
        "One antenna uses 20 reconstructed inputs and two direct saved-I/Q runs.",
    ),
    "difficult": (
        "One antenna on six recordings where both fixed searches missed the target",
        "The six were selected from earlier results. DS29-0082 has a direct one-antenna replay.",
    ),
    "direct": (
        "One antenna from saved radio samples through position on two recordings",
        "DS26-0014 is a hash-selected control. DS29-0082 was a known difficult recording.",
    ),
}
RAW = "full saved I/Q"
PROJECT = "reconstructed antenna records"


def csv_rows(path):
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def old_data():
    seal = earlier.read_receipt(earlier.REPORT, "all-figure-lock.json", PARENT)
    oldgroups = whole_iq.read(fixed.member(earlier.REPORT, seal, "roster.json"))["groups"]
    if sorted(seal["cases"]) != oldgroups["all"]:
        raise ValueError("the four reference options and the scheduled positions must match")
    prior = rows_from(fixed.member(earlier.REPORT, seal, "all-positions.jsonl.gz"))
    by_method = {m: fixed.select(prior, m, oldgroups["all"]) for m in earlier.METHODS}
    times = earlier.timing(prior, oldgroups)
    receipts = whole_iq.read(fixed.member(earlier.REPORT, seal, "inputs.json"))
    for source, digest in receipts.items():
        whole_iq.checked(fixed.SCREEN / source, digest)
    timing_dir = fixed.BASE / "complete-timing"
    timing_lock = whole_iq.read(timing_dir / "prediction-lock.json")
    measured = csv_rows(fixed.member(timing_dir, timing_lock, "resources.csv"))
    fresh_lock = whole_iq.read(earlier.FRESH / "prediction-lock.json")
    fresh = whole_iq.read(fixed.member(earlier.FRESH, fresh_lock, "resources.json"))
    spans = {}
    for ident, span in [
        *((r["id"], float(r["recorded_clock_span_s"])) for r in measured),
        *(
            (i, t["counts"]["window_delivery_span_s"])
            for i, roles in fresh.items()
            for t in roles.values()
        ),
    ]:
        if spans.setdefault(ident, span) != span:
            raise ValueError("methods disagree on the recording's original delivery span")
    for t in times:
        t["call_clock_scope"] = None
        if t["complete_detector_calls"] is not None:
            t["call_clock_scope"] = (
                "dual detector through decoded row"
                if t["method"] == earlier.MIXED
                else "complete dual detector call"
            )
    return oldgroups, by_method, times, spans


def projected_rows(groups, stock):
    plan = earlier.read_receipt(PROJECTED, "plan.json", PROJECTION_PLAN)
    if plan["groups"] != groups:
        raise ValueError("the physical lane study changed the fixed recording roster")
    audit = whole_iq.read(
        whole_iq.checked(PROJECTED / "packet-audit.json", plan["packet_audit_sha256"])
    )
    rows = earlier.prediction_rows(
        PROJECTED, "prediction-lock.json", "positions.jsonl.gz", groups["all"]
    )
    selected = fixed.select(rows, "one_lane_roster", groups["all"])
    jobs = {r["id"]: r for r in plan["jobs"]}
    for ident, row in selected.items():
        fixed.same_capture(row, stock[ident])
        if ident in plan["errors"] and row["result"]["status"] != "ok":
            continue
        job, counts = jobs[ident], audit[ident]
        if (
            row["native_sha256"] != job["native_sha256"]
            or row["stock_native_sha256"] != stock[ident]["native_sha256"]
            or counts["native_archive"]["native_sha256"] != stock[ident]["native_sha256"]
            or counts["masked_probe_rows"] != counts["valid_visits"]
            or counts["valid_visits"] != job["valid_visits"]
        ):
            raise ValueError(
                f"{ident} projected observations disagree with the frozen antenna schedule"
            )
    return selected, audit


def compare_positions(raw, projected):
    fixed.same_capture(raw, projected)
    result = []
    for arm in ARMS:
        endpoints, outcomes = [], []
        for row in (raw, projected):
            fit = row["result"]
            estimate = fit.get("arms", {}).get(arm, {})
            coordinate = estimate.get("latlon")
            state, _ = arm_outcome(fit, estimate)
            outcomes.append("withheld" if state == "ok" and coordinate is None else state)
            endpoints.append(coordinate)
        result.append(
            dict(
                id=raw["id"],
                arm=arm,
                raw_status=outcomes[0],
                projected_status=outcomes[1],
                raw_native_sha256=raw.get("native_sha256"),
                projected_native_sha256=projected.get("native_sha256"),
                coordinate_separation_km=distance_km(*endpoints),
            )
        )
    return result


def direct_rows(stock, projected, audit, spans):
    plan = earlier.read_receipt(DIRECT, "source-lock.json", RAW_PLAN)
    receipt = earlier.read_receipt(DIRECT, "prediction-lock.json")
    ids = sorted(plan["cases"])
    if ids != ["DS26-0014", "DS29-0082"] or sorted(receipt["cases"]) != ids:
        raise ValueError("direct measurements must include the two scheduled raw replays")
    fixed.member(DIRECT, receipt, "source-lock.json")
    rows = rows_from(fixed.member(DIRECT, receipt, "positions.jsonl.gz"))
    raw = fixed.select(rows, "one_lane_whole", ids)
    records = whole_iq.read(fixed.member(DIRECT, receipt, "resources.json"))
    proof = whole_iq.read(fixed.member(DIRECT, receipt, "parity.json"))
    measured, comparisons = {}, []
    for ident, r in raw.items():
        case, w, t = plan["cases"][ident], proof[ident], records[ident]["candidate"]
        fixed.same_capture(stock[ident], r)
        if [r[k] for k in fixed.BINDINGS] != [
            case[k] for k in ("capture_native_sha256", "request_sha256", "catalog_sha256", "tile")
        ] or w["position_status"] != r["result"]["status"]:
            raise ValueError(
                "direct position differs from its scheduled capture or recorded status"
            )
        native = r.get("native_sha256")
        if w["raw_complete"]:
            count = t["counts"]
            if (
                w["stock_native_sha256"] != stock[ident]["native_sha256"]
                or native != w["measured_native_sha256"]
                or native != w["projected_native_sha256"]
                or native != projected[ident]["native_sha256"]
                or not w["same_native_bytes"]
                or not w["selected_lane_equal"]
                or not w["empty_partner_equal"]
                or not w["physical_support_matches"]
                or w["valid_visits"] != count["processed_windows"]
                or w["valid_visits"] != audit[ident]["valid_visits"]
                or w["valid_visits"] != t["dual_calls"]
                or sum(w["receiver_calls"]) != w["valid_visits"]
                or w["invalid_visits"] != count["invalid_capture"]
                or count["window_delivery_span_s"] != spans[ident]
            ):
                raise ValueError(
                    f"{ident} actual one-antenna measurements differ from the projection"
                )
        elif native or r["result"]["status"] == "ok":
            raise ValueError("an incomplete raw acquisition cannot furnish a successful fit")
        for comparison in compare_positions(r, projected[ident]):
            comparisons.append(
                dict(
                    **comparison,
                    raw_complete=w["raw_complete"],
                    valid_visits=w.get("valid_visits"),
                    same_native_bytes=w.get("same_native_bytes"),
                    invalid_visits=w.get("invalid_visits"),
                    selected_lane_equal=w.get("selected_lane_equal"),
                    empty_partner_equal=w.get("empty_partner_equal"),
                )
            )
        raw_time, assembly = t.get("raw_s"), t.get("assembly_s")
        elapsed = raw_time + assembly if raw_time is not None and assembly is not None else None
        measured[ident] = dict(
            earlier.timing_row(
                dict(r, method=ONE, acquisition_evidence=RAW),
                elapsed,
                t.get("position_s"),
                t.get("wall_s"),
                t.get("dual_calls"),
                t.get("within_20ms"),
                case["cpus"],
            ),
            call_clock_scope="complete one-antenna detector call",
        )
    return raw, measured, comparisons


def evaluate(out, rows, groups, clocks, spans, parity):
    authority, original_positions = earlier.fresh_references()
    _, new = earlier.export_references(out, "all", groups["all"], authority, original_positions)
    _, held = held_references(None, [i for i in groups["all"] if i not in new])
    refs = {r["id"]: r for r in held} | new
    scores = fixed.scored(rows, refs)
    scope = {(r["id"], r["method"]): r["acquisition_evidence"] for r in rows}
    for r in scores:
        r["acquisition_evidence"] = scope[r["id"], r["method"]]
    summary = [
        fixed.summary_row(
            [r for r in scores if r["id"] in ids and r["arm"] == arm], ids, cohort, arm, method
        )
        for cohort, ids in groups.items()
        for arm in ARMS
        for method in (*ROLES, *METHODS)
    ]
    budgets = receiver_budget.joined_rows(scores, clocks, spans)
    budget_summary = receiver_budget.summarize(budgets, groups, METHODS)
    for name, table in (
        ("scores", scores),
        ("summary", summary),
        ("timing", clocks),
        ("accuracy-and-time", budgets),
        ("budget-summary", budget_summary),
        ("direct-parity", parity),
        ("calibration-effects", earlier.calibration_effects(scores, groups, METHODS)),
    ):
        csv_file(out / f"{name}.csv", table)
    save_json(
        out / "roster.json", dict(groups=groups, protocol_sha256=_sha(REPORT / "PROTOCOL.md"))
    )
    earlier.render_panels(
        out,
        rows,
        groups,
        authority,
        original_positions,
        prefix="one-lane-benchmark",
        panels=PANELS,
        series=[
            (s, m, LABELS[m])
            for s, m in (
                ("one", ONE),
                ("stock", fixed.FOUR),
                ("one_native_factors", fixed.FIVE),
                ("all_visits", earlier.MIXED),
            )
        ],
        provenance=[
            "inputs.json",
            "roster.json",
            "scores.csv",
            "summary.csv",
            "timing.csv",
            "accuracy-and-time.csv",
            "budget-summary.csv",
            "direct-parity.csv",
            "calibration-effects.csv",
        ],
    )
    receiver_budget_figure.draw(out, budgets, LABELS)
    return summary


def run(out):
    original, methods, clocks, spans = old_data()
    stock = methods[fixed.FOUR]
    projected, audit = projected_rows(original, stock)
    direct, measured, comparisons = direct_rows(stock, projected, audit, spans)
    groups = dict(all=original["all"], difficult=original["difficult"], direct=sorted(direct))
    rows = []
    for ident in groups["all"]:
        for method in earlier.METHODS:
            rows.append(methods[method][ident])
        if ident in direct:
            rows.append(dict(direct[ident], method=ONE, acquisition_evidence=RAW))
            clocks.append(measured[ident])
        else:
            row = dict(projected[ident], method=ONE, acquisition_evidence=PROJECT)
            rows.append(row)
            fit = row.get("position_resources") or {}
            clocks.append(
                dict(
                    earlier.timing_row(row, fit=fit.get("wall_s"), cores=row.get("cpu")),
                    call_clock_scope=None,
                )
            )
    sources = [
        (earlier.REPORT, "all-figure-lock.json"),
        (PROJECTED, "plan.json"),
        (PROJECTED, "prediction-lock.json"),
        (DIRECT, "source-lock.json"),
        (DIRECT, "prediction-lock.json"),
        (DIRECT, "parity.json"),
    ]
    save_json(
        out / "inputs.json",
        {str((d / s).relative_to(fixed.SCREEN)): _sha(d / s) for d, s in sources},
    )
    return evaluate(out, rows, groups, clocks, spans, comparisons)


def show(summary, out):
    by_method = {
        (r["cohort"], r["method"], r["arm"]): r for r in csv_rows(out / "budget-summary.csv")
    }
    labels = LABELS | dict(
        zip(
            ROLES,
            ("v5 no repair", "v5 selective gap", "v5 one omitted", "v5 two omitted"),
            strict=True,
        )
    )
    print(
        "Calibration   Receiver                   Fixes   Within +10%   Median km   P95 km   "
        "Within +10% and replay span / timed"
    )
    for r in summary:
        if r["cohort"] != "all":
            continue
        timed = by_method.get(("all", r["method"], r["arm"]))
        joint = (
            f"{timed['within_10pct_and_span']}/{timed['service_clock_measured']}"
            if timed and int(timed["service_clock_measured"])
            else "—"
        )
        formatted = [f"{r[k]:.3f}" if r[k] is not None else "—" for k in ("median_km", "p95_km")]
        n = r["scheduled"]
        print(
            f"{r['arm']:12} {labels[r['method']]:23} {r['published']:2}/{n:<3}  "
            f"{r['within_10pct']:2}/{n:<3}"
            f"       {formatted[0]:>7}  {formatted[1]:>7}   {joint:>10}"
        )
    print(f"Per-recording positions, call deadlines, replay timing and charts in {out}")
