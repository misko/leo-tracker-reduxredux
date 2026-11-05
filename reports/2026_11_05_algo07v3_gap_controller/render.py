"""Verify ordered-gap and integrated-prefix evidence, then render ownership."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib
from compare_algo07v3_gap_controller import compare_controller, compare_prefix

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(path, bindings):
    rpath = path.with_suffix(".receipt.json")
    receipt = read(rpath)
    members = {str(path): receipt.get("output_sha256") or receipt["output"]["sha256"]}
    members.update({r["path"]: r["sha256"] for r in receipt["modules"].values()})
    if "tool" in receipt:
        members[receipt["tool"]["path"]] = receipt["tool"]["sha256"]
    members.update(receipt.get("tool_sources", {}))
    members.update(receipt.get("additional_inputs", {}))
    for name, digest in receipt["inputs"].items():
        path = Path(name)
        if not path.is_absolute():
            path = Path(receipt["source"]) / path
        members[str(path)] = digest
    for member, digest in members.items():
        if sha(member) != digest:
            raise ValueError("Changed fresh evidence: " + member)
        if member in bindings and bindings[member] != digest:
            raise ValueError("Conflicting source binding: " + member)
    bindings.update(members)
    bindings[str(rpath)] = sha(rpath)
    return receipt


def run(args):
    paths = {
        key: args.evidence / "gap-controller002" / name
        for key, name in (
            ("reference", "reference.json"),
            ("candidate", "candidate.json"),
            ("prefix", "prefix-candidate.json"),
        )
    }
    paths["prefix"] = args.evidence / "gap-controller003/prefix-candidate.json"
    bindings = {}
    receipts = {key: verify(path, bindings) for key, path in paths.items()}
    previous = args.evidence / "replay001/controller-candidate.json"
    previous_sha = "9144935a99b4a877913a63a54bd825816906071faf93bf85a094c011bebc32cb"
    if sha(previous) != previous_sha:
        raise ValueError("Previously qualified prefix changed")
    bindings[str(previous)] = previous_sha
    reference, candidate, prefix = (read(paths[k]) for k in ("reference", "candidate", "prefix"))
    controller = compare_controller(reference, candidate)
    integrated = compare_prefix(read(previous), prefix)
    application_tests = {}
    for label, filename in (("current", "current.xml"), ("prior_eager", "prior-eager.xml")):
        path = args.evidence / "gap-controller003" / filename
        suite = ET.parse(path).getroot().find("testsuite")
        failures = {}
        for case in suite.iter("testcase"):
            for kind in ("failure", "error"):
                failure = case.find(kind)
                if failure is not None:
                    failures[case.attrib["classname"] + "::" + case.attrib["name"]] = dict(
                        kind=kind, message=failure.attrib.get("message", "").splitlines()[0]
                    )
        application_tests[label] = dict(
            tests=int(suite.attrib["tests"]),
            failures=int(suite.attrib["failures"]),
            errors=int(suite.attrib["errors"]),
            cases=failures,
        )
        bindings[str(path)] = sha(path)
    if application_tests["current"]["cases"] != application_tests["prior_eager"]["cases"]:
        raise ValueError("Application failures changed with lazy exports")
    original_init = args.evidence / "gap-controller003/prior-application-init.py"
    bindings[str(original_init)] = sha(original_init)
    summary = dict(
        scope="Ordered gap controller and implemented scientific prefix only",
        complete_path_matched_scans=0,
        complete_path_speedup=None,
        controller=controller,
        integrated_prefix=integrated,
        observed_seconds={k: r["seconds"] for k, r in receipts.items()},
        controlled_speed_benchmark=False,
        application_tests=application_tests,
        artifacts={k: dict(path=str(p), sha256=sha(p)) for k, p in paths.items()},
    )
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n")
    (output / "artifact-bindings.json").write_text(
        json.dumps(bindings, indent=2, sort_keys=True) + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8), layout="constrained")
    panels = [
        (
            "DS26-0012: fresh gap controller",
            {a: controller["owned_points"][a] - 95 for a in controller["owned_points"]},
            controller["owned_points"],
        ),
        (
            "DS26-0002: integrated fitting prefix",
            integrated["protected_points"],
            integrated["resulting_points"],
        ),
    ]
    for ax, (title, before, after) in zip(axes, panels, strict=True):
        x = np.arange(2)
        for shift, counts, color, label in (
            (-0.18, before, "#888888", "Protected incumbent"),
            (0.18, after, "#006d77", "After gap policy"),
        ):
            bars = ax.bar(
                x + shift, [counts[a] for a in ("c0", "fitted_c")], 0.34, color=color, label=label
            )
            ax.bar_label(bars, padding=3, fontsize=9)
        ax.set(
            title=title,
            xticks=x,
            xticklabels=["c = 0", "fitted c"],
            ylim=(0, 3200),
            ylabel="Owned native observations",
        )
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.legend(loc="lower right", fontsize=9)
    fig.suptitle(
        "Exact original controller proof; earlier integrated results unchanged\n"
        "Different validation scopes — full ALGO07 and speedup still unqualified",
        fontsize=11,
    )
    fig.savefig(output / "gap-controller.png", dpi=160)
    plt.close(fig)
    print(json.dumps(dict(controller=controller, integrated_prefix=integrated)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path(__file__).parent)
    run(parser.parse_args())
