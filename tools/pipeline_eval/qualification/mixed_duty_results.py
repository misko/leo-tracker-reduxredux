"""Audit routed packets, then score sealed geography and dual-IQ timing evidence."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, distribution
from ..variants import mixed_duty, selective_capture
from . import support_cross, support_cross_trial
from .full_held_scores import held_references
from .full_v5_check import BULK, _sha
from .margin_admission_inputs import WIDE
from .margin_admission_results import fit, sealed
from .mixed_duty_cost import estimates
from .mixed_duty_trial import CASES, METHODS, REPORT, read, visit_metadata
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .support_cross_results import resources


def position_controls(selection):
    historical = {
        r["id"]: r
        for r in sealed(WIDE, "all-figure-lock.json", "positions.jsonl.gz")
        if r["method"] == "scout-centers_control" and r["id"] in CASES
    }
    exact = [
        r
        for r in sealed(support_cross_trial.REPORT, "prediction-lock.json", "predictions.jsonl.gz")
        if (r["id"], r["condition"]) == ("DS29-0082", "wide")
    ]
    (historical["DS29-0082"],) = exact
    rows = []
    for ident in CASES:
        row, binding = historical[ident], selection["cases"][ident]
        if any(
            row[k] != binding[b]
            for k, b in (
                ("native_sha256", "wide_native_sha256"),
                ("catalog_sha256", "catalogue_sha256"),
                ("original_request_sha256", "capture_request_sha256"),
                ("tile", "tile"),
                ("paired_capture_sha256", "capture_native_sha256"),
            )
        ):
            raise ValueError("wide position control differs from the routed parent")
        rows.append(
            dict(
                row,
                method="mixed_duty_stock_wide",
                condition="wide",
                parent_wide_sha256=binding["wide_native_sha256"],
            )
        )
    return rows


def audit(work, selection, rows):
    results = {(r["id"], r["condition"]): r for r in rows}
    receipt = []
    for ident in CASES:
        item = selection["cases"][ident]
        wide = read(whole_iq.checked(work / f"{ident}-wide.json", item["wide_native_sha256"]))
        case, _ = whole_iq.binding(ident)
        capture = read(
            whole_iq.checked(BULK / case["native"]["path"], item["capture_native_sha256"])
        )
        selective_capture.same_support(wide, capture)
        a, b = (dict(selective_capture.visit_pairs(d["source"]["probes"])) for d in (wide, capture))
        metadata = visit_metadata(wide)
        for mode in METHODS:
            choices = item["decisions"][mode]
            if choices != list(mixed_duty.route(metadata, mode)):
                raise ValueError("the route cannot be reproduced from pure visit metadata")
            selected = {d["visit"] for d in choices}
            entry = results[ident, mode]
            folder = work / ident / mode / "recording"
            native = read(whole_iq.checked(folder / "native.json", entry["native_sha256"]))
            whole_iq.checked(folder / "request.json", entry["prepared_request_sha256"])
            seen = dict(selective_capture.visit_pairs(native["source"]["probes"]))
            support_cross.join(native, wide)
            if len(a) != len(seen) or entries_changed(a, b, seen, selected):
                raise ValueError(
                    "a routed or unrouted visit differs from its complete source packet"
                )
            pos_a = {v for v in selected if any(map(support_cross.positive, a[v]))}
            pos_b = {v for v in selected if any(map(support_cross.positive, b[v]))}
            receipt.append(
                dict(
                    id=ident,
                    condition=mode,
                    visits=len(a),
                    routed=len(selected),
                    changed_packets=sum(a[v] != b[v] for v in selected),
                    routed_channels=[row["channel"] for row in choices],
                    joint_negative_visits=sum(
                        not any(map(support_cross.positive, a[v] + b[v])) for v in a
                    ),
                    selected_joint_negative=len(selected - (pos_a | pos_b)),
                    became_positive=len(pos_b - pos_a),
                    became_negative=len(pos_a - pos_b),
                )
            )
    save_json(REPORT / "treatment-audit.json", receipt)


def entries_changed(wide, capture, actual, selected):
    return list(actual) != list(wide) or any(
        p != (capture if key in selected else wide)[key] for key, p in actual.items()
    )


def time_figure(costs):
    import matplotlib.pyplot as plt

    rows = {r["id"]: r for r in costs if r["condition"] == "rotating"}
    x = [rows[ident]["estimated_cpu_ms"] for ident in CASES]
    low = [r - rows[ident]["box_low_cpu_ms"] for ident, r in zip(CASES, x, strict=True)]
    high = [rows[ident]["box_high_cpu_ms"] - r for ident, r in zip(CASES, x, strict=True)]
    fig, axes = plt.subplots(figsize=(8.7, 4.4), layout="constrained")
    axes.scatter(
        [rows[ident]["actual_stock_cpu_ms"] for ident in CASES],
        CASES,
        color="#4f7190",
        label="Measured stock wide",
        zorder=3,
    )
    axes.errorbar(
        x,
        CASES,
        xerr=[low, high],
        fmt="D",
        capsize=4,
        color="#ad4a17",
        label="Modeled rotating route and original-call sensitivity",
        zorder=3,
    )
    axes.axvline(20, linestyle="--", color="#333333", label="20 ms target")
    axes.invert_yaxis()
    axes.set(
        title="Detector work per admitted dual-receiver visit",
        xlabel="Amortized detector CPU (ms per visit)",
    )
    axes.grid(axis="x", alpha=0.2)
    axes.legend(loc="best")
    fig.savefig(REPORT / "detector-cost.png", dpi=160)
    plt.close(fig)


def figures():
    dependencies = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "treatment-audit.json",
        "time-model.csv",
        "scores.csv",
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(CASES),
            files={name: _sha(REPORT / name) for name in dependencies},
        ),
    )

    def series(key, label, mode):
        return dict(
            key=key,
            label=label,
            file="positions.jsonl.gz",
            value="mixed_duty_" + mode,
            native_field="paired_capture_sha256",
            match=[
                "tile",
                "catalog_sha256",
                "original_request_sha256",
                "parent_wide_sha256",
            ],
        )

    labels = {"rotating": "Low-duty rotating RF route", "fixed_phase": "Low-duty fixed-phase route"}
    save_json(
        REPORT / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="mixed-duty-" + mode.replace("_", "-"),
                    method="mixed_duty_" + mode,
                    scope="roof",
                    cases="sealed",
                    title=label + " for complete recorded GLRT",
                    caption=(
                        "Before detection, one credit per 1,024 valid visits routes the aligned "
                        "stereo packet. Each fit covers the whole acquisition. Two recordings "
                        "are new to this route. Costs use separate measured IQ clocks."
                    ),
                    seal="figure-lock.json",
                    provenance=list(dependencies[1:]),
                    series=[
                        series("one", label, mode),
                        series("stock", "Complete stock wide", "stock_wide"),
                        series("one_native_factors", labels[other], other),
                    ],
                )
                for (mode, label), other in zip(labels.items(), reversed(METHODS), strict=True)
            ],
        ),
    )


def publish(work):
    rows = sealed(REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    selection = read(REPORT / "selection-lock.json")
    if any(_sha(ROOT / name) != digest for name, digest in selection["sources"].items()):
        raise ValueError("the prospective protocol or source differs")
    expected = {(ident, name) for ident in CASES for name in METHODS}
    if len(rows) != len(expected) or {(r["id"], r["condition"]) for r in rows} != expected:
        raise ValueError("all eight scheduled mixtures are required")
    audit(work, selection, rows)
    costs, timing = estimates(selection, work)
    csv_file(REPORT / "time-model.csv", costs)
    save_json(REPORT / "time-authority.json", timing)
    time_figure(costs)
    reference_pack = held_references(None, CASES)[1]
    ref = {r["id"]: r for r in reference_pack}
    csv_file(
        REPORT / "capture-era-v5.csv",
        [
            dict(
                id=ident,
                method=mode,
                arm=arm,
                **{
                    key: case["reference"][mode][arm].get(key)
                    for key in ("status", "error_km", "rf_rms_hz", "wall_s")
                },
            )
            for ident, case in ref.items()
            for mode in ROLES
            for arm in ARMS
        ],
    )
    comparators = position_controls(selection)
    scores = []
    for row in rows + comparators:
        ident = row["id"]
        for arm in ARMS:
            r = fit(row, ref[ident], arm)
            earlier = ref[ident]["reference"]["baseline"][arm].get("error_km")
            scores.append(
                dict(
                    r,
                    condition=row["condition"],
                    original_v5_error_km=earlier,
                    within_10pct_ref=r["error_km"] is not None
                    and earlier is not None
                    and r["error_km"] <= earlier * 1.1,
                )
            )
    csv_file(REPORT / "scores.csv", scores)
    summary = {}
    for mode in (*METHODS, "wide"):
        summary[mode] = {}
        for arm in ARMS:
            matching = [r for r in scores if (r["condition"], r["arm"]) == (mode, arm)]
            summary[mode][arm] = dict(
                attempted=len(matching),
                published=sum(r["published"] for r in matching),
                km=distribution([r["error_km"] for r in matching]),
                conditional_hz=distribution([r["conditional_rf_rms_hz"] for r in matching]),
                within_10pct_original=sum(r["within_10pct_ref"] for r in matching),
            )
    save_json(REPORT / "scores.json", summary)
    csv_file(REPORT / "resources.csv", resources(rows))
    write(REPORT / "positions.jsonl.gz", compressed_rows(rows + comparators))
    figures()
    files = (
        "prediction-lock.json",
        "positions.jsonl.gz",
        "figures.json",
        "figure-lock.json",
        "treatment-audit.json",
        "time-model.csv",
        "time-authority.json",
        "detector-cost.png",
        "scores.csv",
        "scores.json",
        "resources.csv",
        "capture-era-v5.csv",
    )
    save_json(
        REPORT / "score-lock.json",
        dict(
            files={n: _sha(REPORT / n) for n in files},
            exporter_sha256=_sha(Path(__file__)),
            cost_model_sha256=_sha(Path(__file__).with_name("mixed_duty_cost.py")),
            prior_wide_position_lock_sha256=_sha(WIDE / "all-figure-lock.json"),
            hard_case_stock_position_lock_sha256=_sha(
                support_cross_trial.REPORT / "prediction-lock.json"
            ),
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--plot", type=local_output)
    args = parser.parse_args()
    publish(args.work)
    if args.plot:
        from .screening_figures import generate

        generate(args.plot, evidence=REPORT)
