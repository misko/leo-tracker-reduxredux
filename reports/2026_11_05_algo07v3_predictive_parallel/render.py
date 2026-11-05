"""Verify the fresh fold-concurrency pair and render its complete-path timings."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(root):
    out = Path(__file__).resolve().parent
    repo = out.parents[1]
    plan = read(root / "plan002.json")
    for path, digest in plan["source_hashes"].items():
        assert sha(repo / path) == digest, path
    assert sha(root / "serial-job.py") == plan["baseline_job_sha256"]
    assert sha(root / "serial-parallel-adapter.py") == plan["serial_adapter_sha256"]
    comparisons = {n: read(root / n) for n in ("prior-comparison.json", "comparison.json")}
    for value in comparisons.values():
        assert value["exact_owned_science_and_artifacts"] and value["both_c_arms"]
        for path, digest in value["input_bindings"].items():
            assert sha(Path(path)) == digest, path
    current = comparisons["comparison.json"]
    assert current["source_changes"] == plan["comparison_changed_modules"]
    assert current["added_modules"] == plan["comparison_added_modules"]
    assert sorted(comparisons["prior-comparison.json"]["source_changes"]) == sorted(
        plan["prior_comparison_changed_modules"]
    )
    assert not comparisons["prior-comparison.json"]["added_modules"]
    timing, stages, isolation = {}, {}, {}
    for side in ("serial", "parallel"):
        timing[side] = read(root / side / "attempt/supervisor.json")
        value = timing[side]
        assert value["status"] == "exited" and value["returncode"] == 0
        assert value["worker"]["status"] == "complete" and not value["worker"]["resumed"]
        isolation[side] = read(root / side / "isolation.json")
        assert all(isolation[side]["checks"].values())
        log = [
            json.loads(line)
            for line in (root / side / "attempt/worker.log").read_text().splitlines()
        ]
        stages[side] = {r["stage"]: r["seconds"] for r in log if r.get("event") == "stage"}
    assert list(stages["serial"]) == list(stages["parallel"])
    test_paths = [root / n for n in ("tests002.xml", "annotation-tests.xml")]
    suites = [s for path in test_paths for s in ET.parse(path).getroot().iter("testsuite")]
    assert suites and all(
        int(s.attrib[k]) == 0 for s in suites for k in ("failures", "errors", "skipped")
    )
    totals = {s: r["process_seconds"] for s, r in timing.items()}
    summary = dict(
        exact_owned_science_and_publication=True,
        prior_serial_equivalence_verified=True,
        process_seconds=totals,
        observed_pair_ratio=totals["serial"] / totals["parallel"],
        observed_pair_reduction_percent=100 * (1 - totals["parallel"] / totals["serial"]),
        predictive_stage_seconds={s: r["predictive"] for s, r in stages.items()},
        stages=stages,
        tests=sum(int(s.attrib["tests"]) for s in suites),
        test_report_sha256={p.name: sha(p) for p in test_paths},
        qualified_dataset_speedup=None,
        dataset_wide_equivalence=False,
        production_modified=False,
        scope=plan["scope"],
    )
    for name, data in {
        "summary.json": summary,
        "isolation.json": isolation,
        "serial-timing.json": timing["serial"],
        "parallel-timing.json": timing["parallel"],
    }.items():
        (out / name).write_text(json.dumps(data, indent=2) + "\n")
    annotation = read(root / "annotation-comparison.json")
    assert annotation["exact_all_annotation_fields"] and len(annotation["rows"]) == 3
    for path, digest in annotation["inputs"].items():
        assert sha(Path(path)) == digest, path
    for path, digest in annotation["tools"].items():
        assert sha(Path(path)) == digest, path
    for binding in annotation["modules"].values():
        assert sha(Path(binding["path"])) == binding["sha256"], binding["path"]
    for name in (
        "plan.json",
        "plan002.json",
        "comparison.json",
        "prior-comparison.json",
        "annotation-comparison.json",
        "resource-observations.jsonl",
    ):
        (out / name).write_bytes((root / name).read_bytes())
    table = ["| Stage | Serial folds (s) | Concurrent folds (s) |", "| --- | ---: | ---: |"]
    for stage in stages["serial"]:
        table.append(
            f"| {stage} | {stages['serial'][stage]:.3f} | {stages['parallel'][stage]:.3f} |"
        )
    (out / "stage-timings.md").write_text("\n".join(table) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    fig.subplots_adjust(left=0.1, right=0.98, bottom=0.25, top=0.83, wspace=0.65)
    bars = axes[0].bar(
        ["Serial folds", "Concurrent folds"], list(totals.values()), color=["#888888", "#3465a4"]
    )
    axes[0].bar_label(bars, fmt="%.1f s", padding=3)
    axes[0].set(
        ylabel="Native GLRT → publication and outcome (s)", ylim=(0, max(totals.values()) * 1.2)
    )
    largest = sorted(stages["serial"], key=stages["serial"].get, reverse=True)[:7]
    for delta, side, color in ((-0.2, "serial", "#888888"), (0.2, "parallel", "#3465a4")):
        axes[1].barh(
            np.arange(len(largest)) + delta,
            [stages[side][k] for k in largest],
            height=0.4,
            label=side,
            color=color,
        )
    axes[1].set(
        yticks=np.arange(len(largest)),
        yticklabels=[s.replace("_", " ") for s in largest],
        xlabel="Stage wall time (s)",
    )
    axes[1].invert_yaxis()
    axes[1].legend()
    fig.suptitle("DS26-0002 · concurrent predictive folds · exact science and publication")
    fig.text(
        0.5,
        0.04,
        "One sequential pair on a shared host; CPUs 0, 1, 2 and one BLAS thread.\n"
        "Includes both calibration arms, eight PNGs, scientific save and publication.\n"
        "Candidate encountered higher production load; total optimization effect unresolved.\n"
        "Excludes capture, GLRT extraction and queue delay; no dataset-wide speed claim.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(out / "runtime.png", dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    fig.subplots_adjust(bottom=0.25, top=0.82, wspace=0.28)
    cases = [Path(r["fixture_receipt"]).name.split("-reference")[0] for r in annotation["rows"]]
    x = np.arange(len(cases))
    for ax, metric, title in zip(
        axes,
        ("seconds", "cpu_seconds"),
        ("Annotation wall time", "Parent + child CPU time"),
        strict=True,
    ):
        for offset, side, color in ((-0.2, "serial", "#888888"), (0.2, "parallel", "#3465a4")):
            values = [
                next(c[metric] for c in r["comparisons"] if c["side"] == side)
                for r in annotation["rows"]
            ]
            bars = ax.bar(x + offset, values, width=0.4, color=color, label=side)
            ax.bar_label(bars, fmt="%.1f", padding=3)
        ax.set(xticks=x, xticklabels=cases, ylabel="Seconds", title=title)
        ax.set_ylim(0, ax.get_ylim()[1] * 1.12)
        ax.legend()
    fig.suptitle("Complete predictive annotations · every returned proposal field exact")
    fig.text(
        0.5,
        0.04,
        "Frozen-context component comparisons, including both c arms and three grouped folds.\n"
        "Context preparation and the remaining pipeline are excluded.\n"
        "Lower wall time uses more cores; aggregate CPU cost increases about 4.6%.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(out / "annotation-runtime.png", dpi=150)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != "stages"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    render(parser.parse_args().root)
