"""Verify conditional replay evidence and render clipping/reuse behavior."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_inclusion import first_difference
from compare_algo07v3_numerical_recovery import compare

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def verify_fresh(path, bindings):
    rpath = path.with_suffix(".receipt.json")
    receipt = read(rpath)
    members = {str(path): receipt.get("output_sha256") or receipt["output"]["sha256"]}
    members.update({v["path"]: v["sha256"] for v in receipt["modules"].values()})
    for key in ("tool", "numerical_adapter"):
        if key in receipt:
            members[receipt[key]["path"]] = receipt[key]["sha256"]
    members.update(receipt.get("tool_sources", {}))
    inputs = receipt["inputs"]
    if isinstance(inputs, list):
        members.update({v["path"]: v["sha256"] for v in inputs})
    else:
        for name, digest in inputs.items():
            p = Path(name)
            if not p.is_absolute():
                p = Path(receipt["source"]) / p
            members[str(p)] = digest
    members.update(receipt.get("additional_inputs", {}))
    for name, digest in members.items():
        if sha(name) != digest:
            raise ValueError("Changed fresh evidence: " + name)
        if name in bindings and bindings[name] != digest:
            raise ValueError("Conflicting source binding: " + name)
    bindings.update(members)
    bindings[str(rpath)] = sha(rpath)
    return receipt


def run(args):
    root, repo, output = args.evidence, Path(__file__).resolve().parents[2], args.output
    paths = dict(
        annotation_reference=root / "replay002/annotation-reference.json",
        annotation_candidate=root / "replay002/annotation-candidate.json",
        numerical_reference=root / "replay002/inclusion-reference.json",
        controller=root / "replay001/controller-candidate.json",
        previous=root / "joint003/controller-candidate.json",
        shared_reference=root / "inclusion001/DS26-0002-rank0-reference.json",
    )
    bindings = {}
    receipts = {
        k: verify_fresh(paths[k], bindings)
        for k in (
            "annotation_reference",
            "annotation_candidate",
            "numerical_reference",
            "controller",
        )
    }
    # Earlier qualified outputs remain pinned to their committed evidence manifests.
    # Their old source trees are not relabeled as today's tree or requalified here.
    historical = [
        (
            "previous",
            repo / "reports/2026_11_05_algo07v3_joint/controller-bindings.json",
            "bindings",
        ),
        (
            "shared_reference",
            repo / "reports/2026_11_05_algo07v3_inclusion/artifact-bindings.json",
            None,
        ),
    ]
    for key, manifest_path, subkey in historical:
        manifest = read(manifest_path)
        expected = (manifest[subkey] if subkey else manifest)[str(paths[key])]
        if sha(paths[key]) != expected:
            raise ValueError("Qualified historical result changed: " + key)
        bindings[str(paths[key])] = expected
        bindings[str(manifest_path)] = sha(manifest_path)
    docs = {k: read(p) for k, p in paths.items()}
    difference = first_difference(docs["annotation_reference"], docs["annotation_candidate"])
    if difference:
        raise ValueError("Annotation replay differs: " + difference)
    verdict = compare(
        docs["controller"], docs["previous"], docs["shared_reference"], docs["numerical_reference"]
    )
    annotation_path = Path(
        next(
            name
            for name in receipts["annotation_candidate"]["inputs"]
            if name.endswith("/annotation/result.json")
        )
    )
    baseline = read(annotation_path)
    current = docs["annotation_candidate"]["result"]
    before, after, labels = [], [], []
    for i, (old, new) in enumerate(zip(baseline["folds"], current["folds"], strict=True)):
        for arm in ("c0", "fitted_c"):
            before.append(
                sum(
                    h["phase_outside_reference_window"]
                    for h in old["proposals"][0]["arms"][arm]["history"]
                )
            )
            after.append(
                sum(
                    h["phase_outside_reference_window"]
                    for h in new["proposals"][0]["arms"][arm]["history"]
                )
            )
            labels.append(f"Fold {i + 1} · {arm}")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    y = np.arange(len(labels))
    axes[0].barh(y - 0.16, before, 0.32, label="Original ±15 s reference", color="#d58a49")
    axes[0].barh(y + 0.16, after, 0.32, label="Numerical ±30 s reference", color="#2f8c79")
    for i, value in enumerate(after):
        axes[0].text(value + 0.03, i + 0.16, str(value), va="center")
    axes[0].set_yticks(y, labels)
    axes[0].invert_yaxis()
    axes[0].set_ylim(len(labels) + 0.8, -0.6)
    axes[0].set_xlim(0, 1.55)
    axes[0].set_xticks([0, 1])
    axes[0].set_xlabel("Clipped rounds out of five")
    axes[0].set_title("DS26-0044: frozen-competition replay\nIdentity remains ambiguous")
    axes[0].legend(loc="lower right", fontsize=9)
    rows = docs["controller"]["numerical_stage_replay"]
    axes[1].barh(
        range(len(rows)),
        [1] * len(rows),
        color=["#b3d2ed" if r["reused"] else "#f1ca83" for r in rows],
    )
    axes[1].set_yticks(range(len(rows)), [r["name"] for r in rows])
    axes[1].invert_yaxis()
    axes[1].set_xticks([])
    for i, row in enumerate(rows):
        axes[1].text(0.5, i, "REUSED" if row["reused"] else "RECOMPUTED", ha="center", va="center")
    axes[1].set_title(
        "DS26-0002: conditional numerical stages\nPreviously accepted owners all preserved"
    )
    fig.suptitle("ALGO07v3 · exact annotation replay and conditional recovery", fontsize=14)
    fig.text(
        0.5,
        0.02,
        "Candidate selection, aliases, physical priors and c-arm pairing remain fixed. "
        "Full pipeline and ordinary-clock qualification remain pending.",
        ha="center",
        fontsize=10,
    )
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    output.mkdir(parents=True, exist_ok=True)
    fig.savefig(output / "conditional-replay.png", dpi=160)
    plt.close(fig)
    numerical = docs["controller"]["numerical_recovery"]
    summary = dict(
        complete_path_baseline_seconds=None,
        complete_path_candidate_seconds=None,
        complete_path_speedup=None,
        complete_path_matched_scans=0,
        full_pipeline_parity=False,
        annotation_exact=True,
        annotation_status=current["annotation"]["status"],
        annotation_fold_count=len(current["folds"]),
        annotation_proposals_per_fold=[len(f["proposals"]) for f in current["folds"]],
        clipped_training_rounds_before=sum(before),
        clipped_training_rounds_after=sum(after),
        controller=verdict,
        component_seconds={k: v["seconds"] for k, v in receipts.items()},
        component_timings_not_speedup=True,
        selected_norad=numerical["selected"]["targets"][0]["norad"],
        protected_and_recovered_owners={
            a: len(numerical["selected"]["arms"][a]["owners"]) for a in ("c0", "fitted_c")
        },
    )
    (output / "comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps(summary))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
