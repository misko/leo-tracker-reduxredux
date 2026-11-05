"""Verify exact inclusion evidence bindings and plot paired adoption gates."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_inclusion import compare

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Changed evidence: {path}")


def completed(row):
    fit = row["history"][-1].get("fit", row["history"][-1])
    return (
        fit["success"] if "success" in fit else fit.get("stopped") == "small_step_and_improvement"
    )


def run(source, earlier, output):
    rows, bindings = [], {}
    for rank in (0, 1):
        case = f"DS26-0002-rank{rank}"
        paths = {side: source / f"{case}-{side}.json" for side in ("reference", "candidate")}
        docs = {s: json.loads(p.read_text()) for s, p in paths.items()}
        prior = earlier / "DS26-0002-candidate.json"
        verdict = compare(docs["reference"], docs["candidate"], json.loads(prior.read_text()))
        receipts = {
            s: json.loads(p.with_suffix(".receipt.json").read_text()) for s, p in paths.items()
        }
        ref, candidate = receipts["reference"], receipts["candidate"]
        assert ref["scan_identities"] == candidate["scan_identities"]
        assert ref["target_rank"] == candidate["target_rank"] == rank
        check(paths["reference"], ref["output"]["sha256"])
        check(paths["candidate"], candidate["output_sha256"])
        for receipt in receipts.values():
            for item in receipt["modules"].values():
                check(item["path"], item["sha256"])
        for item in ref["inputs"] + [ref["tool"]]:
            check(item["path"], item["sha256"])
        for field in ("tool_sources", "additional_inputs"):
            for path, digest in candidate[field].items():
                check(path, digest)
        for path, digest in candidate["inputs"].items():
            check(Path(candidate["source"]) / path, digest)
        for path in [
            prior,
            *paths.values(),
            *(p.with_suffix(".receipt.json") for p in paths.values()),
        ]:
            bindings[str(path)] = sha(path)
        inclusion = docs["reference"]["predictive_inclusion"]
        annotation = docs["reference"]["predictive_annotation"]
        addition = "target_0" if inclusion["shared_family"] else "new_family"
        phases = [("Initial", inclusion["trial"], inclusion["audit"])]
        if inclusion["retry"]:
            phases.append(
                ("Powell retry", inclusion["retry"]["trial"], inclusion["retry"]["audit"])
            )
        for stage, trial, audit in phases:
            for arm in ("c0", "fitted_c"):
                audits = [r for r in audit["rows"] if r["arm"] == arm]
                control, target = trial["control"]["arms"][arm], trial[addition]["arms"][arm]
                rows.append(
                    dict(
                        rank=rank,
                        component=annotation["result"]["component"],
                        stage=stage,
                        arm=arm,
                        norad=inclusion["annotation"]["norad"],
                        target_points=len(annotation["protocol"]["target"]["observation_ids"]),
                        control_optimizer_completed=completed(control),
                        addition_optimizer_completed=completed(target),
                        control_exact_orbit_owner_audit=next(
                            r["verified"] for r in audits if r["role"] == "control"
                        ),
                        addition_exact_orbit_owner_audit=next(
                            r["verified"] for r in audits if r["role"] == addition
                        ),
                        paired_control_valid=trial["control"]["paired_valid"],
                        paired_addition_valid=trial[addition]["paired_valid"],
                        protected_owner_changes=sum(
                            len(r["incumbent_ownership_changes"]) for r in audits
                        ),
                        lost_points=target["lost_points"],
                        target_objective=float.fromhex(target["negative_twice_elbo"]["hex"]),
                        final_status=inclusion["status"],
                        published_added_points=(
                            inclusion["selected"]["arms"][arm]["added_points"]
                            if inclusion["selected"]
                            else 0
                        ),
                        candidate_full_prefix_seconds=candidate["seconds"],
                        reference_annotation_inclusion_replay_seconds=ref["seconds"],
                        **verdict,
                    )
                )
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(
        json.dumps(
            dict(rows=rows, complete_pipeline_qualified=False, speedup_qualified=False),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    (output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    fields = [
        "control_optimizer_completed",
        "addition_optimizer_completed",
        "control_exact_orbit_owner_audit",
        "addition_exact_orbit_owner_audit",
        "paired_control_valid",
        "paired_addition_valid",
    ]
    labels = [
        "Control\noptimizer",
        "Addition\noptimizer",
        "Control exact\norbit/owner audit",
        "Addition exact\norbit/owner audit",
        "Paired control\nvalid",
        "Paired addition\nvalid",
    ]
    matrix = np.array([[bool(r[k]) for k in fields] for r in rows], dtype=int)
    fig, ax = plt.subplots(figsize=(12, 6.2))
    ax.imshow(matrix, cmap=ListedColormap(["#f5c5bd", "#bee3cf"]), vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(len(fields)), labels, fontsize=10)
    ax.set_yticks(
        range(len(rows)),
        [f"CH{8 if r['rank'] == 0 else 7} · {r['stage']} · {r['arm']}" for r in rows],
    )
    for i, row in enumerate(matrix):
        for j, value in enumerate(row):
            ax.text(j, i, "PASS" if value else "FAIL", ha="center", va="center", fontsize=11)
    ax.set_title(
        "DS26-0002 · standalone v3 exactly reproduces the frozen reference\n"
        "CH8 / 69234: 64-point addition rejected · CH7 / 69213: 35 points accepted after retry",
        pad=16,
    )
    fig.text(
        0.5,
        0.025,
        "Both c arms are required. No incumbent ownership changes.\n"
        "Partial pipeline qualification only; no position-accuracy or complete-path speedup claim.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=[0, 0.09, 1, 1])
    fig.savefig(output / "inclusion-gates.png", dpi=150)
    plt.close(fig)
    print(json.dumps(dict(rows=len(rows), exact=True)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "earlier", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.earlier, args.output)
