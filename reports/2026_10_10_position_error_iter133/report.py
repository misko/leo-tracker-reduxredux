"""Completion-gated evaluation; no reference access before all12 terminal receipts."""

import hashlib
import json
import math
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
NAMES = ("archive", "original", "logparabola", "newton")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def distance(position, reference):
    a, b, c, d = map(math.radians, (*position, *reference))
    h = math.sin((a - c) / 2) ** 2 + math.cos(a) * math.cos(c) * math.sin((b - d) / 2) ** 2
    return 2 * 6371.0088 * math.asin(math.sqrt(min(1, max(0, h))))


def load_receipts(plan, digest, folder):
    output = []
    for binding in plan["members"]:
        path = folder / (binding["label"] + ".json")
        if not path.exists():
            raise ValueError("Not terminal: " + binding["label"])
        result = json.loads(path.read_text())
        if result["label"] != binding["label"] or result["protocol_sha256"] != digest:
            raise ValueError("Foreign receipt")
        if result["status"] not in (
            "complete",
            "failed",
            "attempt-failed",
            "model-integrity-failed",
        ):
            raise ValueError("Unknown terminal status")
        output.append(result)
    return output


def aggregate(rows, arm, name, fallback=False):
    errors, fallbacks = [], 0
    for row in rows:
        value = row["arms"][arm][name]
        if (value is None or not value["qualified"]) and fallback:
            value = row["arms"][arm]["archive"]
            fallbacks += 1
        if value is not None and value["qualified"]:
            errors.append(value["error_km"])
    result = dict(
        expected=len(rows),
        qualified=len(errors),
        archive_fallbacks=fallbacks,
        position_metrics_withheld=len(errors) != len(rows),
    )
    if errors and len(errors) == len(rows):
        result.update(
            mean_km=float(np.mean(errors)),
            median_km=float(np.median(errors)),
            p95_km=float(np.quantile(errors, 0.95)),
            worst_km=float(max(errors)),
        )
    return result


def summarize(rows):
    groups = {
        "full": rows,
        **{d: [r for r in rows if r["dataset"] == d] for d in sorted({r["dataset"] for r in rows})},
    }
    summary, regressions, fallback = {}, {}, {}
    for group, selected in groups.items():
        summary[group], regressions[group], fallback[group] = {}, {}, {}
        for arm in ARMS:
            summary[group][arm] = {name: aggregate(selected, arm, name) for name in NAMES}
            fallback[group][arm] = {
                name: aggregate(selected, arm, name, True) for name in NAMES[1:]
            }
            regressions[group][arm] = {}
            for name in NAMES[2:]:
                pairs = [(r["arms"][arm]["original"], r["arms"][arm][name]) for r in selected]
                delta = [
                    v["error_km"] - b["error_km"]
                    for b, v in pairs
                    if b and v and b["qualified"] and v["qualified"]
                ]
                regressions[group][arm][name] = dict(
                    expected=len(selected),
                    pairs=len(delta),
                    improvements=sum(x < -1e-9 for x in delta),
                    regressions=sum(x > 1e-9 for x in delta),
                    maximum_regression_km=max([0, *delta]),
                    regressing_labels=[
                        r["label"]
                        for r in selected
                        if r["arms"][arm]["original"]
                        and r["arms"][arm][name]
                        and r["arms"][arm]["original"]["qualified"]
                        and r["arms"][arm][name]["qualified"]
                        and r["arms"][arm][name]["error_km"]
                        > r["arms"][arm]["original"]["error_km"] + 1e-9
                    ],
                )
    return dict(
        group_metrics=summary, paired_regressions=regressions, fallback_sensitivity=fallback
    )


def check_evaluation_identity(document, binding, digest):
    clean = binding["case_binding"]
    if document["session_id"] != clean["session_id"]:
        raise ValueError("Evaluation session differs")
    for name in ("input_manifest_sha256", "analysis_manifest_sha256"):
        if document[name] != clean["model_identity"][name]:
            raise ValueError("Evaluation input identity differs: " + name)
    if digest(document["configuration"]["prior"]) != clean["model_identity"]["prior_signature"]:
        raise ValueError("Evaluation prior differs")


def frequency_lineage(binding):
    """Preserve failed128 and corrected134 receipts/cost; no accuracy-based selection."""
    lineage = binding["frequency_lineage"]
    elapsed = binding["frequency_replay_elapsed_s"]
    if not lineage or not np.isfinite(elapsed) or elapsed < 0:
        raise ValueError("Missing/invalid frequency replay lineage")
    values = [entry["elapsed_s"] for entry in lineage]
    if not all(np.isfinite(v) and v >= 0 for v in values):
        raise ValueError("Invalid frequency replay cost")
    if abs(sum(values) - elapsed) > 1e-6:
        raise ValueError("Frequency replay costs differ")
    return dict(attempts=lineage, total_elapsed_s=elapsed)


def frequency_effects(original, candidate):
    """Saved conditional assignment/support diagnostics, never accuracy evidence."""
    fields = ("maximum_responsibility", "assigned_satellite", "clutter_probability")
    diagnostics = [fit.get("frequency_diagnostics") for fit in (original, candidate)]
    if not all(diagnostics):
        return dict(available=False, reason="saved assignment diagnostics unavailable")
    before, after = [{name: np.asarray(value[name]) for name in fields} for value in diagnostics]
    count = len(before[fields[0]])
    if not count or any(v.shape != (count,) for value in (before, after) for v in value.values()):
        raise ValueError("Unmatched frequency diagnostic rows")
    if any(not np.isfinite(v).all() for value in (before, after) for v in value.values()):
        raise ValueError("Nonfinite frequency diagnostics")

    def support(value):
        return dict(
            rows=count,
            assigned_rows=int(np.sum(value["assigned_satellite"] != 0)),
            maximum_responsibility_sum=float(value["maximum_responsibility"].sum()),
            maximum_responsibility_mean=float(value["maximum_responsibility"].mean()),
            nonclutter_mass=float(np.sum(1 - value["clutter_probability"])),
        )

    components = ("frequency_nll", "timing_prior", "nuisance_prior", "total")
    return dict(
        available=True,
        original=support(before),
        candidate=support(after),
        assignment_changes=int(np.sum(before["assigned_satellite"] != after["assigned_satellite"])),
        maximum_responsibility_mean_abs_change=float(
            np.mean(abs(after["maximum_responsibility"] - before["maximum_responsibility"]))
        ),
        clutter_probability_mean_abs_change=float(
            np.mean(abs(after["clutter_probability"] - before["clutter_probability"]))
        ),
        score_components_original=original.get("score_components"),
        score_components_candidate=candidate.get("score_components"),
        score_component_delta={
            name: float(candidate["score_components"][name] - original["score_components"][name])
            for name in components
        }
        if original.get("score_components") and candidate.get("score_components")
        else None,
        interpretation=(
            "nonclutter mass and maximum-label support are conditional in-sample "
            "diagnostics; no independent accuracy claim"
        ),
    )


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    receipts = load_receipts(plan, sha(protocol), HERE / "results")
    # This evaluation port is first opened after every member is terminal.
    port = runpy.run_path(str(ROOT / "reports/2026_10_09_position_error_iter107/report.py"))
    authority_path = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    authority = {
        port["member_label"](m): m for m in json.loads(authority_path.read_text())["members"]
    }
    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.digests import canonical_digest
    from leo.contracts.regional_position import RegionalPrior

    archive_qualification_path = ROOT / "reports/2026_10_10_position_error_iter130/evaluation.json"
    archive_qualification = {
        row["label"]: row for row in json.loads(archive_qualification_path.read_text())["members"]
    }

    rows = []
    for binding, receipt in zip(plan["members"], receipts, strict=True):
        document = port["evaluation_document"](authority[binding["label"]])
        check_evaluation_identity(document, binding, canonical_digest)
        prior = RegionalPrior(**document["configuration"]["prior"])
        reference = (document["reference_latitude_deg"], document["reference_longitude_deg"])
        row = dict(
            label=binding["label"],
            dataset=binding["dataset"],
            status=receipt["status"],
            arms={},
            error=receipt.get("error"),
            attempt_failures={
                name: {
                    arm: attempt.get("error")
                    for arm, attempt in attempts.items()
                    if attempt["status"] != "complete"
                }
                for name, attempts in receipt.get("attempts", {}).items()
            },
            frequency_replay=frequency_lineage(binding),
            frequency_effects={},
        )
        projection = json.loads((ROOT / binding["case_binding"]["projection_path"]).read_text())
        for arm in ARMS:
            row["arms"][arm] = {}
            row["frequency_effects"][arm] = {}
            original_attempt = receipt.get("attempts", {}).get("original", {}).get(arm)
            for name in NAMES[2:]:
                candidate_attempt = receipt.get("attempts", {}).get(name, {}).get(arm)
                if (
                    receipt["status"] != "model-integrity-failed"
                    and original_attempt
                    and candidate_attempt
                    and original_attempt["status"] == "complete"
                    and candidate_attempt["status"] == "complete"
                ):
                    effect = frequency_effects(original_attempt["fit"], candidate_attempt["fit"])
                    effect.update(
                        original_qualified=original_attempt["qualified"],
                        candidate_qualified=candidate_attempt["qualified"],
                    )
                else:
                    effect = dict(
                        available=False, reason="failed/missing attempt or model integrity"
                    )
                row["frequency_effects"][arm][name] = effect
            for name in NAMES:
                attempt = receipt.get("attempts", {}).get(name, {}).get(arm)
                if name == "archive":
                    fit = projection["archive"]["stages"]["B7"][arm]
                    qualified = bool(
                        archive_qualification[binding["label"]]["arms"][arm]["archive"]["qualified"]
                    )
                elif (
                    receipt["status"] == "model-integrity-failed"
                    or not attempt
                    or attempt["status"] != "complete"
                ):
                    row["arms"][arm][name] = None
                    continue
                else:
                    fit, qualified = attempt["fit"], bool(attempt["qualified"])
                row["arms"][arm][name] = dict(
                    error_km=distance(coordinates(prior, np.asarray(fit["vector"])[:2]), reference),
                    qualified=qualified,
                    objective=fit["objective"],
                    posterior_rms_hz=fit.get("posterior_rms_hz"),
                    evaluations=fit.get("evaluations"),
                    elapsed_s=fit.get("elapsed_s"),
                    score_components=fit.get("score_components"),
                )
        rows.append(row)
    payload = dict(
        members=rows, **summarize(rows), runtime_sum_s=sum(r["total_elapsed_s"] for r in receipts)
    )
    payload["frequency_replay_elapsed_sum_s"] = sum(
        r["frequency_replay"]["total_elapsed_s"] for r in rows
    )
    payload["frequency_fit_descriptive"] = {}
    for arm in ARMS:
        payload["frequency_fit_descriptive"][arm] = {}
        for name in NAMES:
            qualified = [
                r["arms"][arm][name]
                for r in rows
                if r["arms"][arm][name] and r["arms"][arm][name]["qualified"]
            ]
            metrics = {}
            for key in (
                "objective",
                "posterior_rms_hz",
                "evaluations",
                "elapsed_s",
                "frequency_nll",
                "timing_prior",
                "nuisance_prior",
            ):
                values = [v.get(key, (v.get("score_components") or {}).get(key)) for v in qualified]
                values = [v for v in values if v is not None]
                metrics[key] = dict(
                    count=len(values), median=float(np.median(values)) if values else None
                )
            payload["frequency_fit_descriptive"][arm][name] = metrics
    (HERE / "evaluation.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(12, 8), constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        for name in NAMES:
            values = [r["arms"][arm][name] for r in rows]
            ax.plot(
                [i for i, v in enumerate(values) if v and v["qualified"]],
                [v["error_km"] for v in values if v and v["qualified"]],
                ".-",
                label=name,
            )
            ax.scatter(
                [i for i, v in enumerate(values) if v and not v["qualified"]],
                [v["error_km"] for v in values if v and not v["qualified"]],
                marker="x",
            )
        ax.set_title(arm)
        ax.set_ylabel("Position error (km)")
        ax.legend()
        ax.set_xticks(range(len(rows)), [r["label"] for r in rows], rotation=45, ha="right")
    fig.savefig(HERE / "comparison.png", dpi=150)
    plt.close(fig)
    lines = [
        "# Matched frequency measurement sensitivity",
        "",
        (
            "All twelve consumed pilot members are reported. Ordinary model, bank, priors and "
            "fitted-derived starts are matched; no variant is selected for deployment. "
            "Frequency score/RMS is separate from geographic accuracy. Archived B7 differs "
            "from fresh same-start control initialization for c=0. Unqualified/raw-integrity "
            "failures withhold full metrics; archive fallback is explicit sensitivity only."
            " Archive qualification is published130 historical comparator provenance, "
            "not new132 qualification (132 checks reconstruction/score parity only)."
        ),
        "",
        "![Position error](comparison.png)",
        "",
        "| Group | Arm | Variant | Qualified | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["group_metrics"].items():
        for arm, variants in arms.items():
            for name, metrics in variants.items():
                vals = [
                    f"{metrics[k]:.6f}" if k in metrics else "withheld"
                    for k in ("mean_km", "median_km", "p95_km", "worst_km")
                ]
                lines.append(
                    f"| {group} | {arm} | {name} | {metrics['qualified']}/{metrics['expected']} | "
                    + " | ".join(vals)
                    + " |"
                )
    lines += [
        "",
        "Paired changes compare refiners with fresh original measurements:",
        "",
        "| Group | Arm | Refiner | Pairs | Improvements | Regressions | Max regression km |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for group, arms in payload["paired_regressions"].items():
        for arm, variants in arms.items():
            for name, metrics in variants.items():
                lines.append(
                    f"| {group} | {arm} | {name} | "
                    f"{metrics['pairs']}/{metrics['expected']} | "
                    f"{metrics['improvements']} | {metrics['regressions']} | "
                    f"{metrics['maximum_regression_km']:.6f} |"
                )
    lines += ["", "Regressing labels (qualified pairs; no tuning from these outcomes):"]
    for group, arms in payload["paired_regressions"].items():
        for arm, variants in arms.items():
            for name, metrics in variants.items():
                labels = ", ".join(metrics["regressing_labels"]) or "none"
                lines.append(f"\n{group}, {arm}, {name}: {labels}.")
    lines += [
        "",
        "Frequency and cost are separate descriptive metrics:",
        "",
        "| Arm | Variant | RMS median Hz (n) | Objective median (n) | Evaluations median (n) |",
        "|---|---|---:|---:|---:|",
    ]
    for arm, variants in payload["frequency_fit_descriptive"].items():
        for name, metrics in variants.items():
            values = []
            for key in ("posterior_rms_hz", "objective", "evaluations"):
                value = metrics[key]
                values.append(
                    (f"{value['median']:.3f}" if value["median"] is not None else "unavailable")
                    + f" ({value['count']})"
                )
            lines.append(f"| {arm} | {name} | " + " | ".join(values) + " |")
    lines += [
        "",
        f"Summed per-member runtime: {payload['runtime_sum_s']:.3f} s; "
        "not parallel wall time. No operational fallback or variant is selected.",
    ]
    lines += [
        "",
        "Qualified score components (median; separate from position accuracy):",
        "",
        "| Arm | Variant | Frequency NLL (n) | Timing prior (n) | Nuisance prior (n) |",
        "|---|---|---:|---:|---:|",
    ]
    for arm, variants in payload["frequency_fit_descriptive"].items():
        for name, metrics in variants.items():
            values = []
            for key in ("frequency_nll", "timing_prior", "nuisance_prior"):
                value = metrics[key]
                values.append(
                    (f"{value['median']:.3f}" if value["median"] is not None else "unavailable")
                    + f" ({value['count']})"
                )
            lines.append(f"| {arm} | {name} | " + " | ".join(values) + " |")
    lines += [
        "",
        "Within-arm saved responsibility/support changes relative to original. "
        "These include complete unqualified fits, explicitly marked; no accuracy inference. "
        "Nonclutter mass is sum(1-clutter probability), not a sample-independence count.",
        "",
        "| Member | Arm | Refiner | Qualified pair | Changed labels | Nonclutter mass delta |",
        "|---|---|---|---|---:|---:|",
    ]
    for row in rows:
        for arm, variants in row["frequency_effects"].items():
            for name, effect in variants.items():
                if effect["available"]:
                    mass = (
                        effect["candidate"]["nonclutter_mass"]
                        - effect["original"]["nonclutter_mass"]
                    )
                    lines.append(
                        f"| {row['label']} | {arm} | {name} | "
                        f"{effect['original_qualified']}/{effect['candidate_qualified']} | "
                        f"{effect['assignment_changes']} | {mass:.6f} |"
                    )
                else:
                    lines.append(f"| {row['label']} | {arm} | {name} | unavailable | — | — |")
    lines += [
        "",
        "Frequency replay lineage preserves the original128 failure and its cost. "
        "DS18-029 originally had 1,782 read failures;134 replays every original observation "
        "after the documented ordinal-reader correction. Other eleven use128. "
        "The original failure receipt remains provenance, not a silently dropped member.",
        "",
        "| Member | Attempt lineage | Attempt elapsed s | Total replay s |",
        "|---|---|---:|---:|",
    ]
    for row in rows:
        replay = row["frequency_replay"]
        attempts = replay["attempts"]
        labels = "; ".join(
            str(entry.get("receipt", entry.get("path"))) + " (" + entry["status"] + ")"
            for entry in attempts
        )
        costs = "; ".join(f"{entry['elapsed_s']:.3f}" for entry in attempts)
        lines.append(f"| {row['label']} | {labels} | {costs} | {replay['total_elapsed_s']:.3f} |")
    lines += [
        "",
        f"Summed frequency replay cost, including original failed128 attempt: "
        f"{payload['frequency_replay_elapsed_sum_s']:.3f} s; separate from final-fit runtime.",
    ]
    lines += [
        "",
        "Complete membership: "
        + ", ".join(r["label"] + " (" + r["status"] + ")" for r in rows)
        + ".",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    paths = [
        protocol,
        authority_path,
        archive_qualification_path,
        HERE / "report.py",
        HERE / "test_report.py",
        HERE / "evaluation.json",
        HERE / "comparison.png",
        HERE / "RESULTS.md",
    ]
    paths += [HERE / "results" / (m["label"] + ".json") for m in plan["members"]]
    integrity = {str(path.relative_to(ROOT)): sha(path) for path in paths}
    (HERE / "report-integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")


if __name__ == "__main__":
    main()
