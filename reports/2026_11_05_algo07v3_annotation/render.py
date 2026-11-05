"""Verify complete annotation parity and render identity/residual diagnostics."""

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_annotation import compare

matplotlib.use("Agg")
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Changed artifact: {path}")


def number(value):
    return float.fromhex(value["hex"])


def run(source, earlier, output):
    rows, bindings = [], {}
    for case in ("DS26-0002", "DS26-0084", "DS26-0102"):
        paths = {s: source / f"{case}-{s}.json" for s in ("reference", "candidate")}
        docs = {s: json.loads(p.read_text()) for s, p in paths.items()}
        prior_path = earlier / f"{case}-candidate.json"
        verdict = compare(docs["reference"], docs["candidate"], json.loads(prior_path.read_text()))
        receipts = {
            s: json.loads(p.with_suffix(".receipt.json").read_text()) for s, p in paths.items()
        }
        ref, candidate = receipts["reference"], receipts["candidate"]
        assert ref["scan_identities"] == candidate["scan_identities"]
        assert ref["target_rank"] == candidate["target_rank"]
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
            prior_path,
            *(p.with_suffix(".receipt.json") for p in paths.values()),
        ]:
            bindings[str(path)] = sha(path)
        result = docs["reference"]["result"]
        votes = []
        for vote in result["annotation"]["votes"]:
            fold = next(f for f in result["folds"] if f["seed"] == vote["seed"])
            proposal = next(p for p in fold["proposals"] if p["norad"] == vote["norad"])
            arm = proposal["arms"][vote["arm"]]
            votes.append(
                dict(
                    vote,
                    margin=number(vote["margin"]),
                    held_RMS_hz=number(arm["scores"]["target"]["rms_hz"]),
                    final_phase_change_s=number(arm["final_phase_change_s"]),
                    minimum_target_elevation_deg=number(arm["minimum_target_elevation_deg"]),
                    held_points=arm["scores"]["target"]["held_residual_hz"]["shape"][0],
                )
            )
        rows.append(
            dict(
                case=case,
                **verdict,
                component=result["component"],
                points=len(docs["reference"]["protocol"]["target"]["observation_ids"]),
                status=result["annotation"]["status"],
                norad=result["annotation"]["norad"],
                votes=votes,
                folds=len(result["folds"]),
                candidate_counts=[len(f["proposals"]) for f in result["folds"]],
                target_enters_calibration_equations=False,
                position_inclusion_authorized=False,
                candidate_full_prefix_seconds=candidate["seconds"],
                reference_annotation_and_replay_seconds=ref["seconds"],
            )
        )
    output.mkdir(parents=True, exist_ok=True)
    document = dict(
        cases=rows,
        full_pipeline_parity=False,
        qualified_speedup=None,
        scope="Complete predictive annotation for the largest recovery target in each scan",
    )
    (output / "comparison.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    fig, axes = plt.subplots(2, 3, figsize=(15, 8), layout="constrained")
    for col, row in enumerate(rows):
        seeds = list(dict.fromkeys(v["seed"] for v in row["votes"]))
        for arm, color, marker in [("c0", "#0072b2", "o"), ("fitted_c", "#d55e00", "s")]:
            chosen = [v for v in row["votes"] if v["arm"] == arm]
            offset = -0.06 if arm == "c0" else 0.06
            x = np.arange(len(chosen)) + offset
            axes[0, col].plot(
                x, [v["held_RMS_hz"] for v in chosen], color=color, marker=marker, label=arm
            )
            axes[1, col].plot(
                x, [v["margin"] for v in chosen], color=color, marker=marker, label=arm
            )
        labels = []
        for seed in seeds:
            winners = sorted({v["norad"] for v in row["votes"] if v["seed"] == seed})
            labels.append(str(seed) + "\n" + ("/".join(map(str, winners))))
        for ax in axes[:, col]:
            ax.set(xticks=range(len(seeds)), xticklabels=labels)
            ax.grid(alpha=0.2)
        axes[0, col].axhline(450, color="black", linestyle="--", label="450 Hz gate")
        axes[0, col].set(
            ylabel="Held prediction RMS (Hz)",
            ylim=(0, 650),
            title=row["case"] + " · " + str(row["points"]) + " points\n" + row["status"],
        )
        axes[1, col].axhline(10, color="black", linestyle="--", label="Required margin: 10")
        axes[1, col].set(
            yscale="log",
            ylabel="Runner-up minus best held score",
            xlabel="Partition seed / preferred NORAD",
        )
    axes[0, 0].legend(fontsize=9)
    axes[1, 0].legend(fontsize=9)
    fig.suptitle(
        "ALGO07v3: exact frozen-reference agreement for every predictive proposal\n"
        "Identity annotation only — target points have not been added to the position fit"
    )
    figure = output / "predictive-validation.png"
    fig.savefig(figure, dpi=150)
    plt.close(fig)
    bindings[str(figure)] = sha(figure)
    (output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps([dict(case=r["case"], status=r["status"], exact=r["exact"]) for r in rows]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "earlier", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.earlier, args.output)
