"""Verify frozen numerical-stage parity and render its measured work and gates."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_joint import compare, flag

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verified(path):
    receipt_path = path.with_suffix(".receipt.json")
    receipt = json.loads(receipt_path.read_text())
    bindings = [receipt["output"], receipt["tool"], *receipt["modules"].values()]
    bindings += [dict(path=p, sha256=h) for p, h in receipt["inputs"].items()]
    for item in bindings:
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("Changed evidence: " + item["path"])
    return json.loads(path.read_text()), receipt, bindings


def run(args):
    phases = [
        ("Original predictive policy", args.default_reference, args.default_candidate),
        ("Numerical recovery policy", args.reference, args.candidate),
    ]
    comparisons, bindings, gates = [], {}, []
    for title, ref_path, cand_path in phases:
        ref, ref_receipt, ref_bindings = verified(ref_path)
        candidate, cand_receipt, cand_bindings = verified(cand_path)
        verdict = compare(ref, candidate)
        comparisons.append(
            dict(
                policy=title,
                **verdict,
                reference_component_seconds=ref_receipt["seconds"],
                candidate_component_seconds=cand_receipt["seconds"],
                controlled_speedup=False,
            )
        )
        for item in ref_bindings + cand_bindings:
            if item["path"] in bindings and bindings[item["path"]] != item["sha256"]:
                raise ValueError("Conflicting source binding: " + item["path"])
            bindings[item["path"]] = item["sha256"]
        for path in (
            ref_path,
            cand_path,
            ref_path.with_suffix(".receipt.json"),
            cand_path.with_suffix(".receipt.json"),
        ):
            bindings[str(path)] = sha(path)
        gates.append([flag(r["audit"]["RF_qualified_arm"]) for r in candidate["records"].values()])
    # json serialization is alphabetical: explicitly choose plotting order.
    methods = [m + "-" + a for m in ("control", "factorized", "joint") for a in ("c0", "fitted_c")]
    baseline = json.loads(args.default_candidate.read_text())
    current = json.loads(args.candidate.read_text())
    policy = current["numerical_policy"]
    if policy["problem_count"] != 36 or len(policy["optimizer_calls"]) != 30:
        raise ValueError("Expected six five-round fits and six audits")
    counts = [[r["nfev"] for r in current["records"][m]["result"]["history"]] for m in methods]
    qualified = [
        [flag(v["records"][m]["audit"]["RF_qualified_arm"]) for v in (baseline, current)]
        for m in methods
    ]
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4), gridspec_kw={"width_ratios": [1.5, 1]})
    im = axes[0].imshow(counts, cmap="YlOrRd", vmin=0, vmax=240, aspect="auto")
    axes[0].set_xticks(range(5), [f"Round {i}" for i in range(1, 6)])
    axes[0].set_yticks(range(6), methods)
    axes[0].set_title("Numerical recovery: physical objective calls\n240-call cap per round")
    for i, row in enumerate(counts):
        for j, value in enumerate(row):
            axes[0].text(j, i, str(value), ha="center", va="center")
    fig.colorbar(im, ax=axes[0], fraction=0.045)
    axes[1].imshow(
        qualified, cmap=ListedColormap(["#f4c2b9", "#bce1cb"]), vmin=0, vmax=1, aspect="auto"
    )
    axes[1].set_xticks([0, 1], ["Predictive\npolicy", "Numerical\nrecovery"])
    axes[1].set_yticks(range(6), methods)
    axes[1].set_title("RF qualification\nEach column matches its frozen reference")
    for i, row in enumerate(qualified):
        for j, value in enumerate(row):
            axes[1].text(j, i, "PASS" if value else "FAIL", ha="center", va="center")
    fig.suptitle("ALGO07v3 standalone numerical recovery · two-family fixture", fontsize=14)
    fig.text(
        0.5,
        0.02,
        "Exact stage parity, including posterior coefficients and evaluation counts. "
        "Not a full-pipeline or localization-accuracy comparison.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.93))
    args.output.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output / "numerical-policy.png", dpi=160)
    plt.close(fig)
    summary = dict(
        complete_path_baseline_seconds=None,
        complete_path_candidate_seconds=None,
        complete_path_speedup=None,
        complete_path_matched_scans=0,
        full_pipeline_parity=False,
        comparisons=comparisons,
        numerical_problem_count=policy["problem_count"],
        numerical_optimizer_calls=len(policy["optimizer_calls"]),
        numerical_reference_updates=len(policy["reference_updates"]),
        numerical_physical_objective_evaluations=int(np.sum(counts)),
        maximum_physical_evaluations_per_round=int(np.max(counts)),
        RF_qualified={
            m: {"predictive": row[0], "numerical": row[1]}
            for m, row in zip(methods, qualified, strict=True)
        },
    )
    (args.output / "comparison.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    (args.output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "default-reference", "default-candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
