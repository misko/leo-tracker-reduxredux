"""Verify joint extraction records and render optimizer/audit outcomes."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
from compare_algo07v3_joint import compare, flag

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path):
    receipt = json.loads(path.with_suffix(".receipt.json").read_text())
    bindings = [receipt["output"], receipt["tool"], *receipt["modules"].values()]
    bindings += [dict(path=p, sha256=h) for p, h in receipt["inputs"].items()]
    for item in bindings:
        if sha(item["path"]) != item["sha256"]:
            raise ValueError("Changed evidence " + item["path"])
    return receipt


def run(args):
    phases = [
        ("L-BFGS-B", args.reference, args.candidate),
        ("Matched Powell retry", args.retry_reference, args.retry_candidate),
    ]
    rows, timings, bindings = [], [], {}
    fig, axes = plt.subplots(1, 2, figsize=(15, 5.3))
    for ax, (stage, reference, candidate) in zip(axes, phases, strict=True):
        expected = json.loads(reference.read_text())
        actual = json.loads(candidate.read_text())
        verdict = compare(expected, actual)
        receipts = [verify(p) for p in (reference, candidate)]
        timings.append(
            dict(
                stage=stage,
                reference_seconds=receipts[0]["seconds"],
                candidate_seconds=receipts[1]["seconds"],
                **verdict,
            )
        )
        for path in (
            reference,
            candidate,
            reference.with_suffix(".receipt.json"),
            candidate.with_suffix(".receipt.json"),
        ):
            bindings[str(path)] = sha(path)
        data, labels = [], []
        for method in ("control", "factorized", "joint"):
            for arm in ("c0", "fitted_c"):
                record = actual["records"][method + "-" + arm]
                fit, audit = record["result"], record["audit"]
                values = [
                    bool(fit["history"][-1]["success"]),
                    all(flag(v["all_pass"]) for v in audit["exact_incumbent_orbits"]),
                    flag(audit["checks"].get("target_gates", True)),
                    flag(audit["checks"].get("phase_resolution", True)),
                    flag(audit["RF_qualified_arm"]),
                ]
                data.append(values)
                labels.append(method + " · " + arm)
                rows.append(
                    dict(
                        stage=stage,
                        method=method,
                        arm=arm,
                        optimizer_success=values[0],
                        exact_incumbent_orbits_pass=values[1],
                        target_gates_pass=values[2],
                        quadrature_pass=values[3],
                        RF_qualified_arm=values[4],
                        owner_changes=len(audit["incumbent_owner_changes"]),
                        reviewed_points=len(audit["reviewed_ids"]),
                        objective=float.fromhex(fit["negative_twice_elbo"]["hex"]),
                        scope_added_points=(
                            len(audit["scope"]["added_validated_target_ids"])
                            if audit["scope"]
                            else 0
                        ),
                    )
                )
        ax.imshow(data, cmap=ListedColormap(["#f4c2b9", "#bce1cb"]), vmin=0, vmax=1, aspect="auto")
        ax.set_yticks(range(6), labels)
        ax.set_xticks(
            range(5),
            [
                "Optimizer",
                "Exact\norbits",
                "Target\nphysical",
                "Phase\nquadrature",
                "RF\nqualified",
            ],
        )
        for i, row in enumerate(data):
            for j, value in enumerate(row):
                text = "N/A" if i < 2 and j in (2, 3) else ("PASS" if value else "FAIL")
                ax.text(j, i, text, ha="center", va="center", fontsize=9)
        ax.set_title(stage)
    fig.suptitle(
        "Standalone joint recovery · exact agreement with frozen ALGO03\n"
        "67188: 27 native points · 64313: 22 native points",
        fontsize=13,
    )
    fig.text(
        0.5,
        0.025,
        "Frozen-context component test: all six fits are retried together. "
        "No incumbent ownership changes.\nFresh target selection, production deadlines "
        "and complete-path speedup require separate qualification.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.1, 1, 0.9])
    args.output.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output / "joint-gates.png", dpi=150)
    plt.close(fig)
    (args.output / "comparison.json").write_text(
        json.dumps(
            dict(rows=rows, timings=timings, full_pipeline_parity=False, speedup_qualified=False),
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    (args.output / "artifact-bindings.json").write_text(
        json.dumps(bindings, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(timings))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "retry-reference", "retry-candidate", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
