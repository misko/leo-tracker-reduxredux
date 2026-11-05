"""Verify bound recovery inventory comparisons and plot native point accounting."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
from compare_algo07v3_inventory import compare

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Changed artifact: {path}")


def run(source, earlier, output):
    rows, bindings = [], {}
    for case in ("DS26-0002", "DS26-0084", "DS26-0102"):
        paths = {side: source / f"{case}-{side}.json" for side in ("reference", "candidate")}
        documents = {s: json.loads(p.read_text()) for s, p in paths.items()}
        previous = earlier / f"{case}-candidate.json"
        verdict = compare(
            documents["reference"], documents["candidate"], json.loads(previous.read_text())
        )
        receipts = {
            s: json.loads(p.with_suffix(".receipt.json").read_text()) for s, p in paths.items()
        }
        ref, candidate = receipts["reference"], receipts["candidate"]
        if ref["scan_identities"] != candidate["scan_identities"]:
            raise ValueError("Different scan identities")
        check(paths["reference"], ref["output"]["sha256"])
        check(paths["candidate"], candidate["output_sha256"])
        for receipt in receipts.values():
            for module in receipt["modules"].values():
                check(module["path"], module["sha256"])
        for item in ref["inputs"] + [ref["tool"]]:
            check(item["path"], item["sha256"])
        for path, digest in candidate["tool_sources"].items():
            check(path, digest)
        for path, digest in candidate["additional_inputs"].items():
            check(path, digest)
        for name, digest in candidate["inputs"].items():
            check(Path(candidate["source"]) / name, digest)
        for path in [
            *paths.values(),
            previous,
            *(p.with_suffix(".receipt.json") for p in paths.values()),
        ]:
            bindings[str(path)] = sha(path)
        result = documents["reference"]
        arms = []
        for summary in result["inventory"]["summary"]:
            arm = summary["arm"]
            arms.append(
                dict(
                    summary,
                    protected_published_points=len(result["publication_support"][arm]["owners"]),
                    postfit_only_points=len(
                        result["publication_support"][arm]["unreported_postfit_ids"]
                    ),
                )
            )
        targets = [
            dict(
                component=r["component"],
                track_id=r["track_id"],
                points=len(r["observation_ids"]),
                inactive_fragment=r["inactive_fragment"],
            )
            for r in result["selected_targets"]
        ]
        rows.append(
            dict(
                case=case,
                **verdict,
                scan_identities=ref["scan_identities"],
                arms=arms,
                eligible_targets=result["eligible_targets"],
                targets=targets,
                candidate_full_prefix_seconds=candidate["seconds"],
                reference_inventory_replay_seconds=ref["seconds"],
            )
        )
    output.mkdir(parents=True, exist_ok=True)
    comparison = dict(
        cases=rows,
        full_pipeline_parity=False,
        qualified_speedup=None,
        scope="Initial search through recovery inventory; subsequent track recovery is unfinished",
    )
    (output / "comparison.json").write_text(json.dumps(comparison, indent=2, sort_keys=True) + "\n")
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout="constrained")
    categories = [
        ("Associated", "#0072b2", lambda r: r["associated"]),
        ("Large remaining graph tracks", "#d55e00", lambda r: r["large_track_unique_points"]),
        (
            "Other remaining graph points",
            "#e69f00",
            lambda r: (
                r["unassociated"] - r["unassociated_outside_graph"] - r["large_track_unique_points"]
            ),
        ),
        ("Outside graph, unassociated", "#bdbdbd", lambda r: r["unassociated_outside_graph"]),
    ]
    for ax, arm in zip(axes, ("c0", "fitted_c"), strict=True):
        values = [next(a for a in r["arms"] if a["arm"] == arm) for r in rows]
        bottom = [0] * len(rows)
        for label, color, get in categories:
            heights = [100 * get(r) / r["total_GLRT"] for r in values]
            ax.bar(range(len(rows)), heights, bottom=bottom, label=label, color=color)
            bottom = [b + h for b, h in zip(bottom, heights, strict=True)]
        for x, r in enumerate(values):
            ax.text(
                x,
                102,
                f"{r['associated']:,}/{r['total_GLRT']:,}\n"
                f"{100 * r['associated'] / r['total_GLRT']:.2f}% associated",
                ha="center",
                va="bottom",
                fontsize=9,
            )
        ax.set(
            xticks=range(len(rows)),
            xticklabels=[r["case"] for r in rows],
            ylim=(0, 114),
            ylabel="Percent of native GLRT winners",
            title=arm,
        )
        ax.grid(axis="y", alpha=0.2)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="outside lower center", ncol=2)
    fig.suptitle(
        "ALGO07v3 recovery inventory: exact reference agreement in both arms\n"
        "Before predictive recovery; these are not final ALGO07 association rates"
    )
    figure = output / "native-point-accounting.png"
    fig.savefig(figure, dpi=160)
    plt.close(fig)
    bindings[str(figure)] = sha(figure)
    (output / "artifact-bindings.json").write_text(
        json.dumps(bindings, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--earlier", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.earlier, args.output)
