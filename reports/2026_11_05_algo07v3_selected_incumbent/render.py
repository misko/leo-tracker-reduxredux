"""Verify all fresh source bindings, compare science, and render retained support."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
from compare_algo07v3_selected_incumbent import KINDS, compare

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
    members = dict(receipt["inputs"])
    members.update({r["path"]: r["sha256"] for r in receipt["modules"].values()})
    for key in ("tool", "output"):
        r = receipt[key]
        members[r["path"]] = r["sha256"]
    for name, expected in members.items():
        if sha(name) != expected:
            raise ValueError("Changed fresh evidence: " + name)
        if name in bindings and bindings[name] != expected:
            raise ValueError("Conflicting source binding: " + name)
    if receipt["side"] == "candidate" and any(
        r["path"].startswith("/opt/") for r in receipt["modules"].values()
    ):
        raise ValueError("Candidate loaded old runtime")
    if receipt["full_pipeline_parity"]:
        raise ValueError("This experiment is not full-path qualification")
    bindings.update(members)
    bindings[str(receipt_path)] = sha(receipt_path)
    return receipt


def run(args):
    bindings, rows = {}, {}
    for mode in KINDS:
        pair = {side: args.evidence / f"{mode}-{side}.json" for side in ("reference", "candidate")}
        receipts = {side: verify(path, bindings) for side, path in pair.items()}
        rows[mode] = compare(read(pair["reference"]), read(pair["candidate"]), mode)
        rows[mode]["output_sha256"] = sha(pair["candidate"])
        rows[mode]["uncontrolled_component_seconds"] = {
            s: r["seconds"] for s, r in receipts.items()
        }
    testpath = args.evidence / "tests.xml"
    suites = ET.parse(testpath).getroot().findall("testsuite")
    counts = {
        k: sum(int(s.get(k, "0")) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    if not counts["tests"] or any(counts[k] for k in ("failures", "errors", "skipped")):
        raise ValueError("Focused test suite did not fully pass")
    bindings[str(testpath)] = sha(testpath)
    bindings[str(Path(__file__).resolve())] = sha(__file__)
    import compare_algo07v3_selected_incumbent as comparator

    bindings[str(Path(comparator.__file__).resolve())] = sha(comparator.__file__)
    args.output.mkdir(parents=True, exist_ok=True)
    summary = dict(
        scope="Selected likelihood and residual preflight, four branches on three scans",
        comparisons=rows,
        tests=counts,
        full_pipeline_parity=False,
        complete_path_speedup=None,
        deployed=False,
    )
    (args.output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    labels = [
        "Baseline\nDS26-0012",
        "Single family\nFresh fixture",
        "Joint families\nDS26-0042",
        "Conditional gap\nDS26-0012",
    ]
    x = np.arange(4)
    for i, (arm, ax) in enumerate(zip(("c0", "fitted_c"), axes, strict=True)):
        retained = np.array([r["retained_points"][arm] for r in rows.values()])
        graph = np.array([r["residual_graph_points"] for r in rows.values()])
        untracked = np.array([r["unassociated_untracked_points"] for r in rows.values()])
        ax.bar(x, retained, color="#267f91", label="Retained associations · exact reference match")
        ax.bar(x, graph, bottom=retained, color="#d4a35b", label="Remaining graph points")
        ax.bar(
            x,
            untracked,
            bottom=retained + graph,
            color="#c8ccd1",
            label="Remaining points outside graph",
        )
        for k, row in enumerate(rows.values()):
            ax.text(k, retained[k] / 2, f"{retained[k]:,}", ha="center", va="center", color="white")
            ax.text(
                k,
                row["total_GLRT"] + 35,
                f"{row['nominated_fragments']} fragments / {row['nominated_points']} pts"
                "\nnomination only",
                ha="center",
                fontsize=8,
            )
        ax.set(
            xticks=x,
            xticklabels=labels,
            ylabel="Native GLRT points",
            ylim=(0, 4900),
            title="c = 0" if i == 0 else "Fitted c",
        )
        ax.grid(axis="y", alpha=0.2)
    fig.suptitle(
        "ALGO07v3 reconstruction preserves selected support\n"
        "No new associations or position estimates in this stage"
    )
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=3, fontsize=8)
    fig.savefig(args.output / "retained-support.png", dpi=150)
    plt.close(fig)
    print(json.dumps(dict(exact_branches=list(rows), tests=counts, full_pipeline_parity=False)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
