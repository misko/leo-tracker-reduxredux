"""Verify selected-checkpoint and residual-screen evidence, then render decisions."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
from compare_algo07v3_residual_screen import compare_prefix, compare_screen, exact

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

OLD_PREFIX_SHA = "c26667e5895dcd92a7b7c463dd83ab5fda5882a8ef6fedef9b7921da19949f4a"


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, bindings):
    receipt_path = path.with_suffix(".receipt.json")
    r = read(receipt_path)
    members = {str(path): r.get("output_sha256") or r["output"]["sha256"]}
    members.update({v["path"]: v["sha256"] for v in r["modules"].values()})
    members.update(r.get("tool_sources", {}))
    members.update(r.get("additional_inputs", {}))
    for key in ("tool", "recovery_catalogue", "preflight_packet"):
        if r.get(key):
            members[r[key]["path"]] = r[key]["sha256"]
    for name, expected in r["inputs"].items():
        p = Path(name)
        members[str(p if p.is_absolute() else Path(r["source"]) / p)] = expected
    if "source" in r:
        summary = Path(r["source"]) / "summary.json"
        upstream = read(summary)
        members[str(summary)] = sha(summary)
        members.update(
            {str(summary.parent / name): value for name, value in upstream["source_files"].items()}
        )
    for name, expected in members.items():
        if sha(name) != expected:
            raise ValueError("Changed fresh evidence: " + name)
        if name in bindings and bindings[name] != expected:
            raise ValueError("Conflicting source binding: " + name)
    if r["side"] == "candidate" and any(
        v["path"].startswith("/opt/") for v in r["modules"].values()
    ):
        raise ValueError("Candidate imported an old installation")
    bindings.update(members)
    bindings[str(receipt_path)] = sha(receipt_path)
    return r


def run(args):
    root, bindings, screens, timings = args.evidence, {}, {}, {}
    for label, folder in [("Fresh-fallback", "screen001"), ("DS26-0183", "screen002")]:
        pair = {side: root / folder / (side + ".json") for side in ("reference", "candidate")}
        receipts = {side: verify(path, bindings) for side, path in pair.items()}
        screens[label] = compare_screen(read(pair["reference"]), read(pair["candidate"]))
        timings[label] = {side: r["seconds"] for side, r in receipts.items()}
    current = root / "checkpoint002"
    catalogue = {}
    for side in ("reference", "candidate"):
        path = current / f"catalogue-{side}.json"
        catalogue[side] = read(path)
        timings["catalogue-" + side] = verify(path, bindings)["seconds"]
    exact(catalogue["reference"], catalogue["candidate"], "Causal catalogue changed")
    previous = root / "gap-controller003/prefix-candidate.json"
    if sha(previous) != OLD_PREFIX_SHA:
        raise ValueError("Archived qualified prefix differs from committed binding")
    bindings[str(previous)] = OLD_PREFIX_SHA
    prefix = current / "prefix-candidate.json"
    prefix_receipt = verify(prefix, bindings)
    prefix_value = read(prefix)
    prefix_check = compare_prefix(read(previous), prefix_value)
    reference_screen = current / "screen-reference.json"
    reference_receipt = verify(reference_screen, bindings)
    if prefix_value["residual_screen"]["status"] != "additional_candidates_screened":
        raise ValueError("Integrated screen did not finish")
    screens["DS26-0002 fresh prefix"] = compare_screen(
        read(reference_screen), prefix_value["residual_screen"]["screen"]
    )
    tests = current / "tests.xml"
    suites = ET.parse(tests).getroot().findall("testsuite")
    counts = {
        k: sum(int(s.get(k, "0")) for s in suites)
        for k in ("tests", "failures", "errors", "skipped")
    }
    if counts["tests"] < 376 or any(counts[k] for k in ("failures", "errors", "skipped")):
        raise ValueError("Focused suite did not fully pass")
    bindings[str(tests)] = sha(tests)
    import compare_algo07v3_residual_screen as comparator

    bindings[str(Path(comparator.__file__).resolve())] = sha(comparator.__file__)
    bindings[str(Path(__file__).resolve())] = sha(__file__)
    summary = dict(
        screens=screens,
        checkpoint=prefix_check,
        catalogue_count=len(catalogue["candidate"]["elements"]),
        tests=counts,
        uncontrolled_component_seconds=timings,
        implemented_prefix_seconds=prefix_receipt["seconds"],
        independent_screen_seconds=reference_receipt["seconds"],
        full_pipeline_parity=False,
        complete_path_speedup=None,
        deployed=False,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    (args.output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), layout="constrained")
    targets = [(label, target) for label, result in screens.items() for target in result["targets"]]
    colors = {True: "#16806a", False: "#bd4b4b"}
    for index, (_label, target) in enumerate(targets):
        for arm, marker, offset in [("c0", "o", -0.13), ("fitted_c", "^", 0.13)]:
            row = target["arms"][arm]
            if row["phase_s"] is None:
                continue
            axes[0].scatter(
                row["phase_s"],
                row["rms_hz"],
                marker=marker,
                s=55,
                c=colors[target["screen_pass"]],
                alpha=0.8,
            )
            if arm == "fitted_c":
                axes[0].annotate(
                    str(index + 1),
                    (row["phase_s"], row["rms_hz"]),
                    xytext=(5, 4),
                    textcoords="offset points",
                    fontsize=9,
                )
            if row["minimum_margin"] is not None:
                axes[1].bar(
                    index + offset,
                    max(row["minimum_margin"], 0.01),
                    width=0.23,
                    color=colors[target["screen_pass"]],
                    alpha=0.6 if arm == "c0" else 1.0,
                )
    axes[0].axvline(-15, color=".6", ls="--", lw=1)
    axes[0].axvline(15, color=".6", ls="--", lw=1)
    axes[0].axhline(450, color=".6", ls=":", lw=1)
    axes[0].set(
        xlabel="Full-data winning phase (s)",
        ylabel="Full-data RMS (Hz)",
        title="Exact decisions: green = screen pass; red = reject",
        xlim=(-31, 31),
    )
    axes[1].axhline(10, color=".5", ls="--", lw=1, label="Required margin: 10 in every fold")
    axes[1].set(
        yscale="log",
        xlabel="Target number (both calibration arms)",
        ylabel="Minimum winner–runner-up margin",
        xticks=np.arange(len(targets)),
        xticklabels=np.arange(1, len(targets) + 1),
        title="Margin alone does not establish acceptance",
    )
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(alpha=0.15)
    fig.suptitle(
        "ALGO07v3 causal residual screen: exact reference matches\n"
        "Circles / light bars: c = 0; triangles / dark bars: fitted c. "
        "Screening is not position acceptance."
    )
    fig.savefig(args.output / "screen-decisions.png", dpi=150)
    plt.close(fig)
    print(json.dumps(dict(checkpoint=prefix_check, tested_targets=len(targets), tests=counts)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
