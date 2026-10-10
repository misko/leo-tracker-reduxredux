"""Full193 completion-gated evaluation, outside the numerical source closure."""

import json
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter135/report.py"))
BASE = API["BASE"]
ARMS = ("fitted-c", "zero-c")
NAMES = ("archive", "timestamp", "phase")
sha = BASE["sha"]


def load_receipts(plan, digest, folder):
    if len(plan["members"]) != 193 or len({m["label"] for m in plan["members"]}) != 193:
        raise ValueError("Exact full193 membership required before evaluation")
    receipts = BASE["load_receipts"](plan, digest, folder)
    hashes = {}
    for binding in plan["members"]:
        path = folder / (binding["label"] + ".json")
        claim = path.with_suffix(".claim.json")
        value = json.loads(claim.read_text())
        if value != dict(label=binding["label"], protocol_sha256=digest):
            raise ValueError("Foreign claim")
        for artifact in (path, claim):
            hashes[str(artifact)] = sha(artifact)
    return receipts, hashes


def summarize(rows):
    groups = API["summarize"](rows)
    for name, group in groups.items():
        subset = rows if name == "full" else [r for r in rows if r["dataset"] == name]
        for arm in ARMS:

            def fallback(row, variant, arm=arm):
                value = row["arms"][arm][variant]
                return value if value and value["qualified"] else row["arms"][arm]["archive"]

            paired = [
                (
                    r["label"],
                    fallback(r, "phase")["error_km"] - fallback(r, "timestamp")["error_km"],
                )
                for r in subset
                if fallback(r, "phase")
                and fallback(r, "timestamp")
                and fallback(r, "phase")["qualified"]
                and fallback(r, "timestamp")["qualified"]
            ]
            group[arm]["fallback_phase_minus_timestamp"] = dict(
                expected=len(subset),
                qualified_pairs=len(paired),
                improvements=sum(d < -1e-9 for _, d in paired),
                regressions=sum(d > 1e-9 for _, d in paired),
                regressing_labels=[label for label, d in paired if d > 1e-9],
                maximum_regression_km=max([0, *(d for _, d in paired)]),
            )
            group[arm]["raw_qualified_subset"] = {}
            for variant in NAMES:
                values = [
                    r["arms"][arm][variant]["error_km"]
                    for r in subset
                    if r["arms"][arm][variant] and r["arms"][arm][variant]["qualified"]
                ]
                group[arm]["raw_qualified_subset"][variant] = dict(
                    expected=len(subset),
                    count=len(values),
                    mean_km=None if not values else float(np.mean(values)),
                    median_km=None if not values else float(np.median(values)),
                    p95_km=None if not values else float(np.quantile(values, 0.95)),
                    worst_km=None if not values else float(max(values)),
                )
            effects = [r.get("frequency_effects", {}).get(arm, {}) for r in subset]
            available = [v for v in effects if v.get("available")]
            group[arm]["frequency_summary"] = dict(
                expected=len(subset),
                available=len(available),
                both_qualified=sum(
                    bool(v.get("timestamp_qualified") and v.get("phase_qualified"))
                    for v in available
                ),
                total_assignment_changes=sum(v["assignment_changes"] for v in available),
                median_component_delta={
                    k: None
                    if not [v for v in available if v.get("score_component_delta")]
                    else float(
                        np.median(
                            [
                                v["score_component_delta"][k]
                                for v in available
                                if v.get("score_component_delta")
                            ]
                        )
                    )
                    for k in ("frequency_nll", "timing_prior", "nuisance_prior", "total")
                },
                interpretation="Conditional saved frequency effects, not accuracy evidence",
            )
            for candidate, baseline in (("timestamp", "archive"), ("phase", "archive")):
                deltas = [
                    (
                        r["label"],
                        r["arms"][arm][candidate]["error_km"]
                        - r["arms"][arm][baseline]["error_km"],
                    )
                    for r in subset
                    if r["arms"][arm][candidate]
                    and r["arms"][arm][candidate]["qualified"]
                    and r["arms"][arm][baseline]
                    and r["arms"][arm][baseline]["qualified"]
                ]
                group[arm][candidate + "_minus_" + baseline] = dict(
                    expected=len(subset),
                    qualified_pairs=len(deltas),
                    improvements=sum(d < -1e-9 for _, d in deltas),
                    regressions=sum(d > 1e-9 for _, d in deltas),
                    regressing_labels=[label for label, d in deltas if d > 1e-9],
                    maximum_regression_km=max([0, *(d for _, d in deltas)]),
                )
    return groups


def plot(rows, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for panels, arm in zip(axes, ARMS, strict=True):
        for name in NAMES:
            available = [
                (i, r["arms"][arm][name])
                for i, r in enumerate(rows)
                if r["arms"][arm][name] is not None
            ]
            qualified = [(i, v["error_km"]) for i, v in available if v["qualified"]]
            panels[0].scatter(
                [i for i, _ in qualified], [v for _, v in qualified], s=12, label=name
            )
            unqualified = [(i, v["error_km"]) for i, v in available if not v["qualified"]]
            if unqualified:
                panels[0].scatter(
                    [i for i, _ in unqualified],
                    [v for _, v in unqualified],
                    marker="x",
                    label=name + " unqualified",
                )
            if len(qualified) == len(rows):
                x = np.sort([v for _, v in qualified])
                panels[1].plot(x, np.arange(1, len(x) + 1) / len(x), label=name)
        panels[0].set(title=arm, xlabel="Frozen member index", ylabel="Position error (km)")
        panels[1].set(
            title=arm + " complete models only",
            xlabel="Position error (km)",
            ylabel="Cumulative fraction",
        )
        for panel in panels:
            panel.grid(alpha=0.2)
            panel.legend()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    digest = sha(protocol)
    receipts, hashes = load_receipts(plan, digest, HERE / "results")
    for group in ("sources", "inputs"):
        for relative, expected in plan[group].items():
            if sha(ROOT / relative) != expected:
                raise ValueError("Frozen input/source changed: " + relative)
    # Evaluation authority is opened only after all193terminal and hash checks.
    authority_path = HERE.parent / "2026_10_09_position_error_iter107/protocol.json"
    if sha(authority_path) != "24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227":
        raise ValueError("Evaluation-only107 authority changed")
    port = runpy.run_path(str(HERE.parent / "2026_10_09_position_error_iter107/report.py"))
    authority = {
        port["member_label"](m): m
        for m in json.loads(
            (HERE.parent / "2026_10_09_position_error_iter107/protocol.json").read_text()
        )["members"]
    }
    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.digests import canonical_digest
    from leo.contracts.regional_position import RegionalPrior

    rows = []
    for binding, receipt in zip(plan["members"], receipts, strict=True):
        document = port["evaluation_document"](authority[binding["label"]])
        BASE["check_evaluation_identity"](document, binding, canonical_digest)
        prior = RegionalPrior(**document["configuration"]["prior"])
        reference = document["reference_latitude_deg"], document["reference_longitude_deg"]
        projection = json.loads((ROOT / binding["case_binding"]["selected_path"]).read_text())
        row = dict(
            label=binding["label"],
            dataset="newer development"
            if binding["label"].startswith("POST18-")
            else binding["label"].split("-")[0],
            membership=binding["case_binding"]["membership"],
            status=receipt["status"],
            error=receipt.get("error"),
            integrity_failures=receipt.get("integrity_failures", []),
            arms={},
            frequency_effects={},
            attempt_details={},
        )
        for arm in ARMS:
            row["attempt_details"][arm] = {}
            row["arms"][arm] = {}
            for name in NAMES:
                attempt = receipt.get("attempts", {}).get(name, {}).get(arm)
                if name != "archive":
                    fit_details = {} if not attempt else attempt.get("fit", {})
                    row["attempt_details"][arm][name] = dict(
                        status="not-run" if not attempt else attempt["status"],
                        error=None if not attempt else attempt.get("error"),
                        qualified=False if not attempt else attempt.get("qualified", False),
                        independent_stationarity=fit_details.get("independent_stationarity"),
                        elapsed_s=None if not attempt else attempt.get("elapsed_s"),
                        model_integrity_usable=receipt["status"] != "model-integrity-failed",
                    )
                if name == "archive":
                    fit = projection["operational"][arm]["fit"]
                    qualified = bool(fit["converged"])
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
                    error_km=BASE["distance"](
                        coordinates(prior, np.asarray(fit["vector"])[:2]), reference
                    ),
                    qualified=qualified,
                    objective=fit["objective"],
                    score_components=fit.get("score_components"),
                    posterior_rms_hz=fit.get("posterior_rms_hz"),
                    qualification_provenance="saved107converged"
                    if name == "archive"
                    else "fresh106independentKKT",
                )
                if name == "archive":
                    state = fit.get("joint_state", {})
                    row["arms"][arm][name]["score_components"] = {
                        "frequency_nll": state.get("likelihood_nll"),
                        "timing_prior": state.get("timing_penalty"),
                        "nuisance_prior": state.get("nuisance_penalty"),
                    }
                    row["arms"][arm][name]["unavailable_archive_diagnostics"] = [
                        "posterior_rms_hz",
                        "responsibility_support",
                        "stationarity",
                        "evaluations",
                    ]
            attempts = [receipt.get("attempts", {}).get(n, {}).get(arm) for n in NAMES[1:]]
            row["frequency_effects"][arm] = (
                BASE["frequency_effects"](attempts[0]["fit"], attempts[1]["fit"])
                if receipt["status"] != "model-integrity-failed"
                and all(a and a["status"] == "complete" for a in attempts)
                else dict(available=False)
            )
            if row["frequency_effects"][arm].get("available"):
                row["frequency_effects"][arm].update(
                    timestamp_qualified=attempts[0]["qualified"],
                    phase_qualified=attempts[1]["qualified"],
                )
        rows.append(row)
    payload = dict(
        members=rows,
        groups=summarize(rows),
        protocol_sha256=digest,
        receipt_sha256=hashes,
        runtime_sum_s=sum(r["total_elapsed_s"] for r in receipts),
    )
    (HERE / "evaluation.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    plot(rows, HERE / "comparison.png")
    lines = [
        "# Full-cohort phase comparison",
        "",
        "All 193 consumed development members are retained. Archive is latest 107 candidate; "
        "fresh timestamp control and phase share fitted-derived starts. No operational winner "
        "is selected. Saved archive qualification is historical; fresh qualification uses "
        "unchanged independent KKT. Frequency fit is separate from accuracy.",
        "",
        "![Position error comparison](comparison.png)",
        "",
        "| Dataset | Arm | Model | Qualified | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["groups"].items():
        for arm, content in arms.items():
            for name, metric in content["metrics"].items():
                values = [
                    str(metric.get(k, "withheld"))
                    for k in ("mean_km", "median_km", "p95_km", "worst_km")
                ]
                lines.append(
                    f"| {group} | {arm} | {name} | {metric['qualified']} | "
                    + " | ".join(values)
                    + " |"
                )
    lines += [
        "",
        "Fallback applies only to unavailable/unqualified/integrity-failed fresh endpoints, "
        "never by true error. Runtime is summed processing cost, not wall time. Archive "
        "frequency RMS/support/stationarity/evaluation counts are unavailable in the lean "
        "projection; no model calls fill these gaps.",
        "",
        "| Dataset | Arm | Fallback model | Fallbacks | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for group, arms in payload["groups"].items():
        for arm, content in arms.items():
            for name, metric in content["archive_fallback_sensitivity"].items():
                lines.append(
                    f"| {group} | {arm} | {name} | {metric['archive_fallbacks']} "
                    + "| "
                    + " | ".join(
                        str(metric.get(k, "withheld"))
                        for k in ("mean_km", "median_km", "p95_km", "worst_km")
                    )
                    + " |"
                )
    lines += [
        "",
        "| Dataset | Arm | Comparison | Pairs | Improved | Regressed | Max regression km |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for group, arms in payload["groups"].items():
        for arm, content in arms.items():
            for key in (
                "paired_phase_minus_timestamp",
                "timestamp_minus_archive",
                "phase_minus_archive",
                "fallback_phase_minus_timestamp",
            ):
                value = content[key]
                lines.append(
                    f"| {group} | {arm} | {key} | {value['qualified_pairs']} "
                    f"| {value['improvements']} | {value['regressions']} "
                    f"| {value['maximum_regression_km']} |"
                )
    lines += [
        "",
        "All member status, exposure labels, regressing labels and separate frequency/prior/"
        "responsibility effects are retained in evaluation.json.",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines) + "\n")
    artifacts = {
        str(HERE / name): sha(HERE / name)
        for name in (
            "protocol.json",
            "report.py",
            "test_report.py",
            "evaluation.json",
            "comparison.png",
            "RESULTS.md",
        )
    }
    (HERE / "report-integrity.json").write_text(
        json.dumps(
            dict(protocol_sha256=digest, artifacts=artifacts, raw_receipt_sha256=hashes), indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
