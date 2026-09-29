"""Descriptive comparison of published fits on the same eighteen scan panels.

No new fits or reference-based selection. Source audit scopes remain distinct.
Run after the four cone/trend summaries are complete, before final publication.
"""
# ruff: noqa: E501 -- Generated Markdown tables and prose.

import hashlib
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BINDINGS = {}
INVENTORIES = {}


def read_bound(path):
    payload = path.read_bytes()
    name = str(path.relative_to(ROOT))
    value = hashlib.sha256(payload).hexdigest()
    report = ROOT / Path(*Path(name).parts[:2])
    inventory_path = report / "evidence-sha256.json"
    if report not in INVENTORIES:
        inventory_bytes = inventory_path.read_bytes()
        inventory = json.loads(inventory_bytes)
        INVENTORIES[report] = inventory.get("sha256", inventory)
        if report != HERE:
            BINDINGS[str(inventory_path.relative_to(ROOT))] = hashlib.sha256(
                inventory_bytes
            ).hexdigest()
    assert INVENTORIES[report][name] == value, name
    BINDINGS[name] = value
    return json.loads(payload)


def distance(point, reference):
    a, b, c, d = map(math.radians, (*point, *reference))
    h = math.sin((c - a) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((d - b) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, h)))


def sources():
    yield "Shared scale, common timing", "consecutive_panels", "scores.json", None, None
    yield "10 s correlated residuals", "consecutive_correlation", "scores.json", None, None
    yield "RX0 only", "receiver_panels", "scores.json", "receiver_id", "0"
    yield "RX1 only", "receiver_panels", "scores.json", "receiver_id", "1"
    yield "Free timing per RX", "split_receiver_timing", "summary.json", None, None
    yield "Common RX timing difference", "pooled_receiver_timing", "summary.json", None, None
    for arm, sigma in (("s010", "0.1"), ("s050", "0.5"), ("s200", "2")):
        yield (
            f"Partial RX timing σ={sigma} s",
            "partial_receiver_timing",
            f"summary-{arm}.json",
            None,
            None,
        )
    yield "Frequency contrasts", "frequency_contrast", "summary.json", None, None
    for arm, name in (("q000", "Normalized visible bank"), ("q020", "Unassociated trend q=0.2")):
        yield name, "unassociated_trend", "summary.json", "arm", arm
    for width in (20, 30, 40, 50):
        yield f"Old soft cone {width}°", "rx_cone_position", f"summary-c{width}.json", None, None
    for width in (20, 30, 40, 50):
        yield f"Cone/trend {width}°", "cone_trend", f"summary-c{width}.json", None, None


def main():
    prior = read_bound(HERE.parent / "2026_09_29_consecutive_panels" / "scores.json")
    plan = read_bound(HERE.parent / "2026_09_29_consecutive_panels" / "plan.json")
    reference = prior["reference"]
    expected = {
        (r["dataset"], r["block"], r["size"]): r["selected"]["session_ids"] for r in prior["rows"]
    }
    assert len(expected) == 18
    origin = plan["config"]["geographic_prior_center_deg"]
    origin_error = distance(origin, reference)
    models = []
    for label, suffix, filename, field, value in sources():
        directory = HERE.parent / ("2026_09_29_" + suffix)
        path = directory / filename
        source = read_bound(path)
        assert source["reference"] == reference
        original = [r for r in source["rows"] if field is None or str(r[field]) == value]
        assert len(original) == 18
        rows = []
        for r in original:
            key = r["dataset"], r["block"], r["size"]
            selected = r.get("selected")
            if "selected" not in r:
                selected = read_bound(directory / "runs" / r["unit"] / "selection.json")["selected"]
            error = None
            if selected is not None:
                # These models expand each recording into RX0 and RX1 documents.
                copies = (
                    2
                    if suffix
                    in (
                        "split_receiver_timing",
                        "pooled_receiver_timing",
                        "partial_receiver_timing",
                    )
                    else 1
                )
                assert selected["session_ids"] == expected[key] * copies
                estimate = selected["estimate"]
                error = distance((estimate["latitude_deg"], estimate["longitude_deg"]), reference)
                assert abs(error - r["error_m"]) < 1e-4
            if "validated" in r:
                valid = r["validated"]
                scope = "Source all-parameter audit"
            elif "audit_passed" in r:
                valid = r["audit_passed"]
                scope = "Source all-parameter audit"
            else:
                checks = r["gradient_check"]
                valid = (
                    selected is not None
                    and selected["qualified"]
                    and len(checks) == 4
                    and all(c["absolute_difference"] < 0.002 for c in checks)
                )
                scope = "Source geographic-coordinate audit"
            assert isinstance(valid, bool)
            rows.append(
                {
                    "dataset": key[0],
                    "block": key[1],
                    "size": key[2],
                    "unit": r["unit"],
                    "source_audit_passed": valid,
                    "error_m": error,
                }
            )
        assert {(r["dataset"], r["block"], r["size"]) for r in rows} == expected.keys()
        valid = [r for r in rows if r["source_audit_passed"]]
        medians = {}
        for dataset in ("DS7", "DS8", "DS9"):
            for size in (4, 8):
                subset = [r for r in rows if r["dataset"] == dataset and r["size"] == size]
                assert len(subset) == 3
                medians[f"{dataset}_{size}"] = (
                    float(np.median([r["error_m"] for r in subset]))
                    if all(r["source_audit_passed"] for r in subset)
                    else None
                )
        models.append(
            {
                "label": label,
                "source": str(path.relative_to(ROOT)),
                "report": str((directory / "README.md").relative_to(ROOT)),
                "scope": scope,
                "both_receivers": field != "receiver_id",
                "audited": len(valid),
                "planned": 18,
                "nominal_sub_km": sum(r["error_m"] < 1000 for r in valid),
                "better_than_inherited_origin": sum(r["error_m"] < origin_error for r in valid),
                "worst_audited_error_m": max(r["error_m"] for r in valid),
                "worst_dataset_eight_scan_median_m": max(
                    medians[f"{d}_8"] for d in ("DS7", "DS8", "DS9")
                )
                if all(medians[f"{d}_8"] is not None for d in ("DS7", "DS8", "DS9"))
                else None,
                "medians_m": medians,
                "rows": rows,
            }
        )
    write_outputs(models, origin_error)


def write_outputs(models, origin_error):
    assert len(models) == 20
    ranking = sorted(
        [m for m in models if m["both_receivers"] and m["audited"] == 18],
        key=lambda m: m["worst_dataset_eight_scan_median_m"],
    )
    with (HERE / "model-comparison.json").open("x") as f:
        json.dump(
            {
                "models": models,
                "inherited_origin_error_m": origin_error,
                "descriptive_rank_by_worst_dataset_eight_scan_median": [
                    m["label"] for m in ranking
                ],
            },
            f,
            indent=2,
            allow_nan=False,
        )
    columns = [f"{d}_{s}" for d in ("DS7", "DS8", "DS9") for s in (4, 8)]
    values = np.array(
        [
            [m["medians_m"][c] if m["medians_m"][c] is not None else np.nan for c in columns]
            for m in models
        ]
    )
    fig, ax = plt.subplots(figsize=(10.5, 11))
    palette = plt.get_cmap("YlOrRd").copy()
    palette.set_bad("lightgray")
    im = ax.imshow(values, vmin=0, vmax=3500, cmap=palette, aspect="auto")
    ax.set_xticks(range(6), [c.replace("_", " / ") for c in columns])
    ax.set_yticks(range(len(models)), [m["label"] for m in models])
    for i, row in enumerate(values):
        for j, v in enumerate(row):
            ax.text(
                j,
                i,
                f"{v:.0f}" if np.isfinite(v) else "Incomplete",
                ha="center",
                va="center",
                fontsize=8,
            )
    ax.set_title(
        "Median joint-set error (m); exposed unsurveyed reference\nGray cells lack a complete three-block source audit"
    )
    fig.colorbar(im, ax=ax, label="Error (m)", fraction=0.03, extend="max")
    fig.tight_layout()
    for suffix in ("png", "svg"):
        fig.savefig(HERE / f"model-comparison.{suffix}", dpi=160)
    plt.close(fig)
    lines = [
        "# Completed approaches on the same consecutive scan sets",
        "",
        "This is a descriptive comparison of twenty completed model arms on the fixed early/middle/late four/eight panels. "
        "It reuses each source's training-selected fit; it does not select starts or beamwidths using reference error. "
        "Four-scan sets are nested in eight-scan sets, and all results come from the same previously explored site.",
        "",
        f"**The inherited search center is already {origin_error:.1f} m from the exposed, unsurveyed reference.** "
        "This is a context check, not a radio-derived estimate or a proposed solution. Nominal sub-km counts alone "
        "therefore cannot demonstrate information gain, blind accuracy or calibrated resolution.",
        "",
        "Each median below requires all three block results to pass their source's audit. "
        "The original shared-scale, correlated and RX-only reports audit geographic coordinates; later reports also audit timing coordinates. "
        "These are source audit statuses, not a new common numerical certification. RX-only arms use a subset of the observations.",
        "",
        "| Approach | DS7 / 4 | DS7 / 8 | DS8 / 4 | DS8 / 8 | DS9 / 4 | DS9 / 8 | Source audits | Sub-km sets |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in models:
        link = "../" + Path(m["report"]).parts[1] + "/README.md"
        cells = [
            f"{m['medians_m'][c]:,.0f}" if m["medians_m"][c] is not None else "Incomplete"
            for c in columns
        ]
        lines.append(
            f"| [{m['label']}]({link}) | "
            + " | ".join(cells)
            + f" | {m['audited']}/18 | {m['nominal_sub_km']}/{m['audited']} |"
        )
    lines += [
        "",
        "All errors are metres. Failed or unaudited results remain in the machine-readable comparison; they are not silently dropped from a median.",
        "",
        "![Matched scan-set comparison](model-comparison.png)",
        "",
        "## Descriptive ranking, not a model-selection experiment",
        "",
        "Among both-RX arms with all eighteen source audits passing, order by the largest of the three dataset eight-scan medians. "
        "This post-hoc display emphasizes performance across datasets; it is not a preregistered selection rule. "
        "Worst-panel errors and counts beating the inherited origin expose failures hidden by medians.",
        "",
        "| Order | Approach | Worst dataset eight-scan median (m) | Worst panel (m) | Better than inherited origin |",
        "|---:|---|---:|---:|---:|",
    ]
    for i, m in enumerate(ranking, 1):
        lines.append(
            f"| {i} | {m['label']} | {m['worst_dataset_eight_scan_median_m']:,.0f} | {m['worst_audited_error_m']:,.0f} | {m['better_than_inherited_origin']}/18 |"
        )
    lines += [
        "",
        "Do not rank held log scores across these different density constructions. Within-model matched held comparisons remain in the source reports. "
        "Predictive gains have repeatedly occurred without geographic gains. The full-dataset fits and earlier single-scan studies "
        "use different sample counts and are summarized separately in [the earlier approach overview](../2026_09_29_approach_summary/README.md).",
        "",
        "All selected positions were checked against the same reference with independent distance arithmetic, "
        "and session membership was matched to the original eighteen panels. Source summaries and selected-fit "
        "artifacts were checked against their evidence inventories. [Complete comparison](model-comparison.json) "
        "retains every panel, source path and audit status. No new geographic fits were run.",
        "",
    ]
    with (HERE / "MODEL-COMPARISON.md").open("x") as f:
        f.write("\n".join(lines))
    inventory_path = HERE / "evidence-sha256.json"
    bindings = json.loads(inventory_path.read_text())["sha256"]
    for name, value in BINDINGS.items():
        assert name not in bindings or bindings[name] == value
        bindings[name] = value
    for path in HERE.rglob("*"):
        if path.is_file() and "__pycache__" not in path.parts and path != inventory_path:
            bindings[str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    inventory_path.write_text(json.dumps({"sha256": bindings}, indent=2))
    print("Verified", len(models), "model arms on 18 matched panels; origin error", origin_error)


if __name__ == "__main__":
    main()
