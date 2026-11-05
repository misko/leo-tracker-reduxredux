"""Verify gap component evidence and render its native points and owner counts."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, bindings):
    receipt_path = path.with_suffix(".receipt.json")
    receipt = read(receipt_path)
    members = {str(path): receipt["output"]["sha256"], **receipt["inputs"]}
    members.update({r["path"]: r["sha256"] for r in receipt["modules"].values()})
    members[receipt["tool"]["path"]] = receipt["tool"]["sha256"]
    for member, digest in members.items():
        if sha(member) != digest:
            raise ValueError("Changed fresh evidence: " + member)
        if member in bindings and bindings[member] != digest:
            raise ValueError("Conflicting source: " + member)
    bindings.update(members)
    bindings[str(receipt_path)] = sha(receipt_path)
    return receipt


def number(value):
    return float.fromhex(value["hex"])


def run(args):
    root, output = args.evidence, args.output
    paths = dict(
        annotation_reference=root / "gap003/reference.json",
        annotation_candidate=root / "gap003/candidate.json",
        inclusion_reference=root / "gap002/inclusion-reference.json",
        inclusion_candidate=root / "gap002/inclusion-candidate.json",
        default_candidate=root / "gap003/default-joint-candidate.json",
    )
    bindings = {}
    receipts = {key: verify(path, bindings) for key, path in paths.items()}
    for prefix in ("annotation", "inclusion"):
        if paths[prefix + "_reference"].read_bytes() != paths[prefix + "_candidate"].read_bytes():
            raise ValueError(prefix + " scientific mismatch")
    default_digest = "efd1dc11516547837bd5a0f3ee63f160dea431cd9503570ca6f46724e4f3a1c3"
    if sha(paths["default_candidate"]) != default_digest:
        raise ValueError("Default predictive policy changed")
    annotation = read(paths["annotation_candidate"])
    fit = read(paths["inclusion_candidate"])
    branch_path = next(
        p
        for p in receipts["inclusion_reference"]["inputs"]
        if p.endswith("/gap-source/branches.json")
    )
    branches = read(branch_path)["branches"]
    branch = next(b for b in branches if b["branch_id"] == "1f5732beec965a2bec1e")
    tracks_path = next(
        p for p in receipts["inclusion_reference"]["inputs"] if p.endswith("/SCAN/tracks.json")
    )
    parent = read(tracks_path)[branch["parent_index"]]
    counts = {
        arm: [
            len(fit["trial"][role]["arms"][arm]["proposed_owners"])
            for role in ("control", "target_0")
        ]
        for arm in ("c0", "fitted_c")
    }
    summary = dict(
        scope="Component qualification; gap controller and full pipeline incomplete",
        complete_path_matched_scans=0,
        complete_path_speedup=None,
        annotation_exact=True,
        inclusion_exact=True,
        default_joint_unchanged=True,
        branch_points=len(branch["observation_ids"]),
        parent_points=len(parent["observation_ids"]),
        norad=annotation["annotation"]["result"]["annotation"]["norad"],
        minimum_identity_margin=number(
            annotation["annotation"]["result"]["annotation"]["minimum_margin"]
        ),
        owner_counts=counts,
        all_exact_audits_verified=fit["audit"]["all_verified"],
        paired_valid=fit["trial"]["target_0"]["paired_valid"],
        target_metrics={
            arm: {
                key: number(row["shared_satellite_replay"][key])
                for key in ("maximum_phase_linearization_error_hz", "receiver_coefficient_change")
            }
            for arm, row in fit["trial"]["target_0"]["arms"].items()
        },
        observed_seconds={key: r["seconds"] for key, r in receipts.items()},
        timing_is_benchmark=False,
        artifacts={key: dict(path=str(path), sha256=sha(path)) for key, path in paths.items()},
    )
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12, 4.6), layout="constrained")
    ax.scatter(
        parent["times"],
        np.asarray(parent["values"]) / 1000,
        c="0.65",
        s=24,
        label=f"Parent: {len(parent['times'])} native points",
    )
    ax.scatter(
        branch["times_s"],
        np.asarray(branch["values_hz"]) / 1000,
        c="#006d77",
        s=12,
        label=f"Eligible fragment: {len(branch['times_s'])} points",
    )
    ax.set(
        xlabel="Time within scan (s)",
        ylabel="Alias-unwrapped GLRT CFO (kHz)",
        title="DS26-0012: timing-only fragment, NORAD 63635",
    )
    ax.legend(fontsize=9)
    for index, values in enumerate(counts.values()):
        x = np.array([index * 3, index * 3 + 1])
        bars = bx.bar(x, values, color=["0.65", "#006d77"])
        bx.bar_label(bars, padding=3)
    bx.set(
        xticks=[0, 1, 3, 4],
        xticklabels=[
            "Control\nc = 0",
            "+ fragment\nc = 0",
            "Control\nfitted c",
            "+ fragment\nfitted c",
        ],
        ylim=(0, 2900),
        ylabel="Owned native observations",
        title="95 added points in each matched arm",
    )
    for axis in (ax, bx):
        axis.grid(alpha=0.2)
        axis.set_axisbelow(True)
    fig.suptitle(
        "Frozen reference = standalone component, exact scientific fingerprints\n"
        "Receiver coefficients unchanged; complete-pipeline qualification still pending",
        fontsize=11,
    )
    fig.savefig(output / "gap-recovery.png", dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            {k: summary[k] for k in ("branch_points", "parent_points", "norad", "owner_counts")}
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    run(parser.parse_args())
