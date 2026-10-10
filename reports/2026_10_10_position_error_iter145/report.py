"""Post-seal paired-emission evaluation; references are evaluation-only."""
# ruff: noqa: E501

import json
import runpy
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter133/report.py"))
ARMS = ("fitted-c", "zero-c")
NAMES = ("archive", "control", "rho25")
sha = BASE["sha"]


def load_terminal(plan, digest, directory, root):
    members = plan["members"]
    if len(members) != 12 or len({m["label"] for m in members}) != 12:
        raise ValueError("Exact twelve-member coverage required")
    for group in ("sources", "inputs"):
        for name, expected in plan[group].items():
            if sha(root / name) != expected:
                raise ValueError("Frozen source/input changed")
    receipts = BASE["load_receipts"](plan, digest, directory)
    for member in members:
        claim = directory / (member["label"] + ".claim.json")
        if json.loads(claim.read_text()) != dict(label=member["label"], protocol_sha256=digest):
            raise ValueError("Foreign claim")
    return receipts


def paired(rows, arm, before, after):
    deltas = []
    for row in rows:
        a, b = (row["arms"][arm][name] for name in (before, after))
        if a and b and a["qualified"] and b["qualified"]:
            deltas.append(dict(label=row["label"], delta_km=b["error_km"] - a["error_km"]))
    return dict(
        expected=len(rows),
        qualified_pairs=len(deltas),
        complete_matched_coverage=len(deltas) == len(rows),
        improvements=sum(d["delta_km"] < -1e-9 for d in deltas),
        regressions=sum(d["delta_km"] > 1e-9 for d in deltas),
        regressions_over_1km=sum(d["delta_km"] > 1 for d in deltas),
        maximum_regression_km=max([0, *[d["delta_km"] for d in deltas]]),
        deltas=deltas,
    )


def summarize(rows):
    groups = {
        "full": rows,
        **{d: [r for r in rows if r["dataset"] == d] for d in sorted({r["dataset"] for r in rows})},
    }

    return {
        group: {
            arm: dict(
                metrics={name: BASE["aggregate"](selected, arm, name) for name in NAMES},
                archive_to_control=paired(selected, arm, "archive", "control"),
                control_to_correlated=paired(selected, arm, "control", "rho25"),
            )
            for arm in ARMS
        }
        for group, selected in groups.items()
    }


def pairing_counts(pairing):
    if pairing is None:
        return dict(available=False)
    pairs, unpaired = pairing["pairs"], pairing["unpaired"]
    indices = [i for pair in pairs for i in pair] + [r["index"] for r in unpaired]
    if sorted(indices) != list(range(pairing["observations"])):
        raise ValueError("Pair support lost or repeated observations")
    return dict(
        available=True,
        observations=pairing["observations"],
        pairs=len(pairs),
        paired_rows=2 * len(pairs),
        unpaired_rows=len(unpaired),
        unpaired_reasons=pairing["reason_counts"],
    )


def plot(rows, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    for pair, arm in zip(axes, ARMS, strict=True):
        for name in NAMES:
            selected = [(i, r["arms"][arm][name]) for i, r in enumerate(rows)]
            available = [(i, v["error_km"]) for i, v in selected if v and v["qualified"]]
            if available:
                pair[0].plot(
                    [i for i, _ in available],
                    [v for _, v in available],
                    "o",
                    label=f"{name} {len(available)}/{len(rows)}",
                )
            if len(available) == len(rows):
                values = np.sort([v for _, v in available])
                pair[1].step(
                    values, np.arange(1, len(values) + 1) / len(values), where="post", label=name
                )
        pair[0].set(
            title=arm,
            ylabel="Position error (km)",
            xticks=range(len(rows)),
            xticklabels=[r["label"] for r in rows],
        )
        pair[0].tick_params(axis="x", rotation=65)
        pair[1].set(
            title="Complete model coverage only", xlabel="Position error (km)", ylabel="ECDF"
        )
        for ax in pair:
            ax.legend()
            ax.grid(alpha=0.2)
    fig.savefig(path, dpi=150)
    plt.close(fig)


def markdown(payload):
    lines = [
        "# Fixed correlated-emission pilot",
        "",
        f"Globally frozen geometry: {payload.get('physics', 'unspecified synthetic fixture')}.",
        "",
        "All twelve consumed development members remain in coverage. The globally fixed rho=0.25 "
        "hypothesis is compared with a fresh rho=0 control; no objective-based model winner is "
        "selected. Archived B7 is a separate historical comparator. Both c arms use matched "
        "observations, pairs, bank, priors and fitted-derived starts; c=0 locks RF terms.",
        "",
        "Frequency RMS uses updated conditional marginal responsibilities and is descriptive. "
        "Improved likelihood or RMS does not establish improved localization, covariance "
        "calibration or independent validation. Full accuracy metrics are withheld for incomplete "
        "qualification; no failed member is imputed or silently replaced by archive.",
        "",
        "![Position errors](comparison.png)",
        "",
        "| Dataset | Arm | Model | Qualified | Mean km | Median km | p95 km | Worst km |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for dataset, arms in payload["groups"].items():
        for arm, content in arms.items():
            for name, m in content["metrics"].items():
                values = " | ".join(
                    f"{m[k]:.6f}" if k in m else "withheld"
                    for k in ("mean_km", "median_km", "p95_km", "worst_km")
                )
                lines.append(
                    f"| {dataset} | {arm} | {name} | {m['qualified']}/{m['expected']} | {values} |"
                )
    lines += [
        "",
        "| Dataset | Arm | Comparison | Qualified pairs | Better | Worse | >1 km worse | Max regression km |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for dataset, arms in payload["groups"].items():
        for arm, content in arms.items():
            for comparison in ("archive_to_control", "control_to_correlated"):
                p = content[comparison]
                lines.append(
                    f"| {dataset} | {arm} | {comparison} | {p['qualified_pairs']}/{p['expected']} | {p['improvements']} | {p['regressions']} | {p['regressions_over_1km']} | {p['maximum_regression_km']:.6f} |"
                )
    lines += [
        "",
        "| Member | Terminal status | Pair/support coverage | Attempt failures |",
        "|---|---|---|---|",
    ]
    for row in payload["members"]:
        lines.append(
            f"| {row['label']} | {row['status']} | {json.dumps(row['pairing'])} | {json.dumps(row['attempt_failures'])} |"
        )
    lines += [
        "",
        "| Member | Arm | Model | Qualified | Objective | Updated-marginal RMS Hz | Fit seconds |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in payload["members"]:
        for arm in ARMS:
            for name in NAMES:
                value = row["arms"][arm][name]
                if value:
                    lines.append(
                        f"| {row['label']} | {arm} | {name} | {value['qualified']} | {value['objective']:.8g} | {value.get('posterior_rms_hz')} | {value.get('elapsed_s')} |"
                    )
    lines += [
        "",
        "Objective values belong to different emission models and are not an operational "
        "selection rule. All raw qualification/score/support fields and per-member paired "
        "changes are retained in [evaluation.json](evaluation.json). Archive qualification "
        "is historical provenance, not a newly fitted control. No full-cohort or deployment "
        "gain is inferred from this conditional pilot.",
    ]
    return "\n".join(lines) + "\n"


def main():
    protocol = HERE / "protocol.json"
    plan = json.loads(protocol.read_text())
    receipts = load_terminal(plan, sha(protocol), HERE / "results", ROOT)
    # Reference-bearing authorities are opened only after the full terminal/hash gate.
    authority_path = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    historical_path = ROOT / "reports/2026_10_10_position_error_iter130/evaluation.json"
    if sha(authority_path) != "24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227":
        raise ValueError("Evaluation authority changed")
    if sha(historical_path) != "95db2c66053fab6b9e406a3c8aff073b4c4872a06e2a8093590642bed74496f4":
        raise ValueError("Historical archive qualification changed")
    port = runpy.run_path(str(ROOT / "reports/2026_10_09_position_error_iter107/report.py"))
    authority = {
        port["member_label"](m): m for m in json.loads(authority_path.read_text())["members"]
    }
    historical = {r["label"]: r for r in json.loads(historical_path.read_text())["members"]}
    from leo.analysis.regional_position_score import coordinates
    from leo.contracts.digests import canonical_digest
    from leo.contracts.regional_position import RegionalPrior

    rows = []
    for binding, receipt in zip(plan["members"], receipts, strict=True):
        document = port["evaluation_document"](authority[binding["label"]])
        BASE["check_evaluation_identity"](document, binding, canonical_digest)
        prior = RegionalPrior(**document["configuration"]["prior"])
        reference = (document["reference_latitude_deg"], document["reference_longitude_deg"])
        projection = json.loads((ROOT / binding["case_binding"]["projection_path"]).read_text())
        row = dict(
            label=binding["label"],
            dataset=binding["dataset"],
            status=receipt["status"],
            error=receipt.get("error"),
            pairing=pairing_counts(receipt.get("pairing")),
            support_binding=binding.get("support_binding"),
            physics=receipt.get("physics", plan["physics"]),
            integrity_failures=receipt.get("integrity_failures", []),
            total_elapsed_s=receipt["total_elapsed_s"],
            arms={},
            attempt_failures={},
        )
        for arm in ARMS:
            row["arms"][arm] = {}
            for name in NAMES:
                attempt = receipt.get("attempts", {}).get(name, {}).get(arm)
                if name == "archive":
                    fit = projection["archive"]["stages"]["B7"][arm]
                    qualified = historical[binding["label"]]["arms"][arm]["archive"]["qualified"]
                elif (
                    receipt["status"] == "model-integrity-failed"
                    or not attempt
                    or attempt["status"] != "complete"
                ):
                    row["arms"][arm][name] = None
                    row["attempt_failures"][name + "/" + arm] = (
                        attempt.get("error", "unavailable") if attempt else "missing"
                    )
                    continue
                else:
                    fit, qualified = attempt["fit"], bool(attempt["qualified"])
                row["arms"][arm][name] = dict(
                    error_km=BASE["distance"](
                        coordinates(prior, np.asarray(fit["vector"])[:2]), reference
                    ),
                    qualified=qualified,
                    **{
                        key: fit.get(key)
                        for key in (
                            "objective",
                            "posterior_rms_hz",
                            "evaluations",
                            "elapsed_s",
                            "score_components",
                            "independent_stationarity",
                            "stop_reason",
                            "frequency_diagnostics",
                            "reported_converged",
                        )
                    },
                )
        rows.append(row)
    payload = dict(
        members=rows,
        groups=summarize(rows),
        physics=plan["physics"],
        runtime_sum_s=sum(r["total_elapsed_s"] for r in receipts),
    )
    (HERE / "evaluation.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    plot(rows, HERE / "comparison.png")
    (HERE / "RESULTS.md").write_text(markdown(payload))
    artifacts = {
        name: sha(HERE / name)
        for name in (
            "evaluation.json",
            "comparison.png",
            "RESULTS.md",
            "report.py",
            "test_report.py",
        )
    }
    integrity = dict(
        protocol_sha256=sha(protocol),
        receipts={
            str((HERE / "results" / (m["label"] + suffix)).relative_to(ROOT)): sha(
                HERE / "results" / (m["label"] + suffix)
            )
            for m in plan["members"]
            for suffix in (".json", ".claim.json")
        },
        artifacts=artifacts,
        evaluation_provenance={
            str(p.relative_to(ROOT)): sha(p) for p in (authority_path, historical_path)
        },
    )
    (HERE / "REPORT_INTEGRITY.json").write_text(json.dumps(integrity, indent=2) + "\n")


if __name__ == "__main__":
    main()
