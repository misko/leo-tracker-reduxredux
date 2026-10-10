"""Reporting-only sealed DS16-020 successor; no model evaluation or fit."""

import hashlib
import json
import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ARMS = ("fitted-c", "zero-c")
BRANCHES = ("native", "fixed")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(plan, digest, read_phase, evaluate):
    """References are reachable only after all three same-protocol receipts seal."""
    receipts = {p: read_phase(p) for p in ("search", *BRANCHES)}
    for phase, row in receipts.items():
        if row.get("protocol_sha256") != digest or row.get("label") != "DS16-020":
            raise ValueError("foreign successor receipt")
        if row.get("status") != "complete":
            raise ValueError("all successor phases must be complete before evaluation")
        if phase != "search":
            if row.get("branch") != phase or row.get("fallback_available") is not False:
                raise ValueError("foreign branch or undeclared fallback")
            for arm in ARMS:
                if not (row.get("operational", {}).get(arm, {}).get("fit", {}).get("converged")):
                    raise ValueError("unqualified selected endpoint")
    values = {
        arm: {branch: evaluate(receipts[branch]["operational"][arm]) for branch in BRANCHES}
        for arm in ARMS
    }
    for arm in ARMS:
        values[arm]["delta_km"] = (
            values[arm]["fixed"]["error_km"] - values[arm]["native"]["error_km"]
        )
    compact = runpy.run_path(
        str(ROOT / "reports/2026_10_09_position_error_iter129/report_cohort.py")
    )["compact_receipt"]
    return dict(
        label="DS16-020",
        session_id=plan["members"][0]["membership"]["session_id"],
        exposure=plan["members"][0]["exposure"],
        arms=values,
        phases={p: compact(row) for p, row in receipts.items()},
        total_actual_elapsed_s=sum(row["elapsed_s"] for row in receipts.values()),
        original129_failure_preserved=True,
        independent_validation=False,
    )


def main():
    from leo.contracts.digests import canonical_digest

    protocol = HERE / "protocol.json"
    if sha(protocol) != "5732e0e1f30e6bc4dc719a34915d57e7d2966273272b6fd64c6e5cd832ea7ae8":
        raise ValueError("successor protocol changed")
    plan = json.loads(protocol.read_text())
    for group in ("source_sha256", "input_sha256"):
        for name, digest in plan[group].items():
            if sha(ROOT / name) != digest:
                raise ValueError("frozen binding changed: " + name)
    phase_paths = {p: HERE / "results/DS16-020" / p / "result.json" for p in ("search", *BRANCHES)}
    authority_path = ROOT / "reports/2026_10_09_position_error_iter107/protocol.json"
    if sha(authority_path) != "24df105bf4618947162f9438ea2a77115d1baa134a00b5f7b48279942848d227":
        raise ValueError("evaluation authority changed")
    authority = json.loads(authority_path.read_text())
    member = next(
        m
        for m in authority["members"]
        if m["member"].get("inventory_label", m["member"].get("dataset_label")) == "DS16-020"
    )
    if member["member"]["session_id"] != plan["members"][0]["membership"]["session_id"]:
        raise ValueError("evaluation session differs")
    evaluator = runpy.run_path(str(authority_path.parent / "report.py"))
    document = None

    def evaluate(operation):
        nonlocal document
        if document is None:
            document = evaluator["evaluation_document"](member)
            inference = json.loads(
                (ROOT / plan["members"][0]["binding"]["document_path"]).read_text()
            )
            for key in ("session_id", "input_manifest_sha256", "evidence_sha256"):
                if document[key] != inference[key]:
                    raise ValueError("evaluation input differs: " + key)
            if document["configuration"]["prior"] != inference["configuration"]["prior"]:
                raise ValueError("evaluation prior differs")
        return evaluator["evaluate_fit"](operation, document)

    summary = collect(
        plan, canonical_digest(plan), lambda p: json.loads(phase_paths[p].read_text()), evaluate
    )
    summary["receipt_sha256"] = {str(p.relative_to(ROOT)): sha(p) for p in phase_paths.values()}
    summary["protocol_file_sha256"] = sha(protocol)
    original_path = (
        ROOT / "reports/2026_10_09_position_error_iter129/results/DS16-020/search/result.json"
    )
    original = json.loads(original_path.read_text())
    if original["status"] != "failed" or original["label"] != "DS16-020":
        raise ValueError("original failure changed")
    summary["original129_failed_receipt_sha256"] = sha(original_path)
    summary["original129_failure_elapsed_s"] = original["elapsed_s"]
    summary["original129_failure_reason"] = original["reason"]
    summary["combined_original_plus_successor_elapsed_s"] = (
        original["elapsed_s"] + summary["total_actual_elapsed_s"]
    )
    (HERE / "SUMMARY.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(8, 3.8))
    for axis, arm in zip(axes, ARMS, strict=True):
        v = summary["arms"][arm]
        errors = [v[b]["error_km"] for b in BRANCHES]
        axis.bar(BRANCHES, errors, color=["#7a7a7a", "#7041a8"])
        for i, error in enumerate(errors):
            axis.text(i, error, f"{error:.4f}", ha="center", va="bottom")
        axis.set_title(arm)
        axis.set_ylabel("Position error (km)")
        axis.set_ylim(0, max(errors) * 1.25)
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
    fig.suptitle("DS16-020 · separately budgeted clean-admission successor")
    fig.tight_layout()
    fig.savefig(HERE / "position_errors.png", dpi=160)
    plt.close(fig)
    lines = [
        "# DS16-020: separately budgeted clean-admission successor",
        "",
        "All three successor phases are complete. Iteration 129's original admission failure "
        "and both skipped branches remain unchanged. This consumed one-member experiment is "
        "reported separately; it does not fill iteration 129's missing pair or establish "
        "generalization.",
        "",
        "![Matched c-arm position errors](position_errors.png)",
        "",
        "| Arm | Native error km | Fixed error km | Fixed minus native km | "
        "Native / fixed frequency RMS Hz | Native / fixed objective |",
        "|---|---:|---:|---:|---|---|",
    ]
    for arm in ARMS:
        v = summary["arms"][arm]
        n, f = v["native"], v["fixed"]
        lines.append(
            f"| {arm} | {n['error_km']:.6f} | {f['error_km']:.6f} | "
            f"{v['delta_km']:+.6f} | {n['posterior_rms_hz']:.3f} / "
            f"{f['posterior_rms_hz']:.3f} | {n['objective']:.6f} / {f['objective']:.6f} |"
        )
    lines += [
        "",
        "Positive delta means a fixed-bank regression. Objectives/frequency fit are "
        "descriptive: discovery, regions and fitted-led support may differ across policies. "
        "No cross-policy objective winner was selected. Both final c arms have matched "
        "observations, priors and search budgets within each policy.",
        "",
        f"Actual saved phase time: search {summary['phases']['search']['elapsed_s']:.3f}s, "
        f"native {summary['phases']['native']['elapsed_s']:.3f}s, "
        f"fixed {summary['phases']['fixed']['elapsed_s']:.3f}s; "
        f"total {summary['total_actual_elapsed_s']:.3f}s. This added successor cost is "
        f"separate from the original iteration 129 failure ({original['elapsed_s']:.9f}s). "
        f"Original plus successor actual cost is "
        f"{summary['combined_original_plus_successor_elapsed_s']:.9f}s; "
        "the scheduled iteration 135 intermission is not charged as compute time.",
        "",
        "All four selected B7 endpoints independently qualified at the unchanged 0.001 KKT "
        "gate. All six retained calibrations qualified. Regional final qualification was "
        "15/18 for native and 17/18 for fixed; joint-stage qualification was 12/12 and 11/12. "
        "The fixed zero-c B4 intermediate failed qualification; its final B7 endpoint qualified. "
        "Every unqualified attempt remains reported, without selection as an endpoint. All 36 "
        "regional final attempts and "
        "joint-stage qualifications are retained in [the compact summary](SUMMARY.json). "
        "Raw receipts remain local, with hashes published; no remote raw replay bundle "
        "is claimed. References were accessed only after both successor branches sealed.",
        "",
    ]
    (HERE / "RESULTS.md").write_text("\n".join(lines))
    names = ("SUMMARY.json", "RESULTS.md", "position_errors.png", "report.py")
    (HERE / "INTEGRITY.json").write_text(
        json.dumps({n: sha(HERE / n) for n in names}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
