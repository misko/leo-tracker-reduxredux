"""Completion-gated mean/product decomposition; no position/reference imports."""

import json
import math
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter136/report.py"))
ARMS = ("fitted-c", "zero-c")


def compact(value):
    blocks = [b for row in value["group_satellite_records"] for b in row["blocks"]]
    eligible = [b for b in blocks if b["crossprediction_status"] == "available"]
    mass = sum(b["mass"] for b in eligible)
    raw = sum(b["weighted_product_sum"] for b in eligible)
    centered = sum(b["opposite_block_centered_product_sum"] for b in eligible)
    for field, actual in (
        ("crossprediction_mass", mass),
        ("crossprediction_raw_product_sum", raw),
        ("crossprediction_centered_product_sum", centered),
    ):
        if not math.isfinite(actual) or not math.isclose(
            actual, value[field], abs_tol=1e-10, rel_tol=1e-12
        ):
            raise ValueError("decomposition receipt mismatch: " + field)
    result = {
        key: value[key]
        for key in (
            "pairs",
            "shared_label_mass",
            "weighted_product_sum",
            "crossprediction_mass",
            "crossprediction_raw_product_sum",
            "crossprediction_centered_product_sum",
            "excluded_crossprediction_mass",
            "frequency_nll",
            "archive_objective_delta",
        )
    }
    result.update(
        raw_matched_per_mass=raw / mass if mass else None,
        centered_matched_per_mass=centered / mass if mass else None,
        mass_coverage=mass / value["shared_label_mass"] if value["shared_label_mass"] else None,
        group_satellite_records=value["group_satellite_records"],
    )
    return result


def aggregate(rows):
    output = {}
    for arm in ARMS:
        values = [row["arms"][arm] for row in rows]
        fields = (
            "pairs",
            "shared_label_mass",
            "weighted_product_sum",
            "crossprediction_mass",
            "crossprediction_raw_product_sum",
            "crossprediction_centered_product_sum",
            "excluded_crossprediction_mass",
        )
        result = {field: sum(v[field] for v in values) for field in fields}
        mass = result["crossprediction_mass"]
        result.update(
            raw_matched_per_mass=result["crossprediction_raw_product_sum"] / mass if mass else None,
            centered_matched_per_mass=result["crossprediction_centered_product_sum"] / mass
            if mass
            else None,
            mass_coverage=mass / result["shared_label_mass"]
            if result["shared_label_mass"]
            else None,
        )
        output[arm] = result
    return output


def summarize(plan, receipts):
    if set(receipts) != {m["label"] for m in plan["members"]}:
        raise ValueError("full membership required")
    rows = []
    for member in plan["members"]:
        raw = receipts[member["label"]]
        row = dict(
            label=member["label"],
            dataset=member["dataset"],
            status=raw["status"],
            error=raw.get("error"),
            elapsed_s=raw["total_elapsed_s"],
        )
        if raw["status"] == "complete":
            row.update(
                observations=raw["observations"],
                unpaired_reasons=raw["pairing"]["reason_counts"],
                support_unavailable_reasons=raw["support"]["unavailable_reasons"],
                arms={arm: compact(raw["arms"][arm]) for arm in ARMS},
            )
        rows.append(row)
    complete = all(r["status"] == "complete" for r in rows)
    groups = {"pooled": aggregate(rows)} if complete else {}
    if complete:
        for dataset in sorted({r["dataset"] for r in rows}):
            groups[dataset] = aggregate([r for r in rows if r["dataset"] == dataset])
    return dict(
        complete=complete,
        members=rows,
        summaries=groups,
        elapsed_s=sum(r["elapsed_s"] for r in rows),
        interpretation="Descriptive only; no fitted rho, significance or position accuracy",
    )


def prepare(here=HERE, root=ROOT):
    plan, receipts, hashes = BASE["load"](here, root)
    result = summarize(plan, receipts)
    prior = []
    for member in plan["members"]:
        path = root / member["predecessor_receipt"]
        value = json.loads(path.read_text())
        if (
            value["label"] != member["label"]
            or value["protocol_sha256"] != plan["predecessor_protocol_sha256"]
        ):
            raise ValueError("foreign138 lineage")
        prior.append(
            dict(
                label=member["label"],
                status=value["status"],
                elapsed_s=value["total_elapsed_s"],
                receipt=member["predecessor_receipt"],
            )
        )
    result.update(
        raw_sha256=hashes,
        protocol_sha256=BASE["sha"](here / "protocol.json"),
        iteration138=prior,
        iteration136=plan["predecessor_failures"],
    )
    result["lineage_elapsed_s"] = result["elapsed_s"] + sum(
        r["elapsed_s"] for rows in (prior, plan["predecessor_failures"]) for r in rows
    )
    return result


def markdown(result):
    lines = [
        "# Conditional residual means versus products",
        "",
        "All twelve terminal members remain in coverage. "
        "Cohort summaries are withheld if any member failed.",
        "",
        "Raw and opposite-block-centered products below use exactly the same eligible fractional "
        "mass. Zero training/target mass is unavailable, not zero evidence. Nuisance parameters "
        "and soft responsibilities were fitted on the full recording: these are not independent "
        "validation predictions, covariance estimates, significance tests or accuracy results.",
        "",
        "| Member | Arm | Status | Eligible mass | Excluded mass | "
        "Matched raw / mass | Centered / mass |",
        "|---|---|---|---:|---:|---:|---:|",
    ]

    def fmt(value):
        return "unavailable" if value is None else f"{value:.6g}"

    for row in result["members"]:
        if row["status"] != "complete":
            lines.append(f"| {row['label']} | both | failed: {row['error']} | — | — | — | — |")
        for arm, value in row.get("arms", {}).items():
            fields = [
                value[k]
                for k in (
                    "crossprediction_mass",
                    "excluded_crossprediction_mass",
                    "raw_matched_per_mass",
                    "centered_matched_per_mass",
                )
            ]
            lines.append(
                f"| {row['label']} | {arm} | complete | " + " | ".join(map(fmt, fields)) + " |"
            )
    lines += [
        "",
        "## Dataset and pooled summaries",
        "",
        "```json",
        json.dumps(result["summaries"], indent=2),
        "```",
        "",
        "Per-group/satellite/block means and products, full raw scores, shared-label mass, "
        "support reasons, failures, runtimes and receipt hashes are retained in `summary.json`.",
        "",
        f"This run: {result['elapsed_s']:.3f} seconds. Including preserved iteration 136 failures "
        f"and iteration 138 audit: {result['lineage_elapsed_s']:.3f} seconds.",
    ]
    if result["complete"]:
        lines += ["", "![Matched residual-product decomposition](decomposition.png)"]
    return "\n".join(lines) + "\n"


def plot(result, path):
    if not result["complete"]:
        raise ValueError("complete matched coverage required")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), sharex=True, constrained_layout=True)
    rows = result["members"]
    for axis, arm in zip(axes, ARMS, strict=True):
        for key, label in (
            ("raw_matched_per_mass", "Raw: matched subset"),
            ("centered_matched_per_mass", "Opposite-block centered"),
        ):
            axis.plot(
                range(len(rows)),
                [
                    r["arms"][arm][key] if r["arms"][arm][key] is not None else float("nan")
                    for r in rows
                ],
                "o-",
                label=label,
            )
        axis.axhline(0, color="gray", linewidth=0.8)
        axis.set_title(arm + ": conditional decomposition, not covariance")
        axis.set_ylabel("Weighted product / eligible mass")
        axis.legend()
    axes[-1].set_xticks(range(len(rows)), [r["label"] for r in rows], rotation=45, ha="right")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    result = prepare(HERE, ROOT)
    (HERE / "summary.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    (HERE / "RESULTS.md").write_text(markdown(result))
    if result["complete"]:
        plot(result, HERE / "decomposition.png")


if __name__ == "__main__":
    main()
