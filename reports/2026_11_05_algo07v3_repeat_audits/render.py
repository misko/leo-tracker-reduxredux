"""Bind the completed reverse-order timing repeat and historical audit checks."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(root, audit):
    out = Path(__file__).resolve().parent
    repo = out.parents[1]
    plan = read(root / "plan.json")
    for path, expected in plan["source_hashes"].items():
        assert digest(repo / path) == expected, path
    assert digest(root / "serial-job.py") == plan["baseline_job_sha256"]
    comparison = read(root / "comparison.json")
    assert comparison["exact_owned_science_and_artifacts"] and comparison["both_c_arms"]
    assert comparison["source_changes"] == plan["comparison_changed_modules"]
    assert comparison["added_modules"] == plan["comparison_added_modules"]
    for path, expected in comparison["input_bindings"].items():
        assert digest(Path(path)) == expected, path
    historical = read(audit / "comparison002.json")
    assert historical["all_checked_values_exact"] and not historical["errors"]
    assert len(historical["mapped_policies"]) == 15
    assert historical["missing_audit_mappings"] == ["additional_recovery", "numerical_recovery"]
    for binding in historical["input_bindings"].values():
        assert "sha256:" + digest(Path(binding["path"])) == binding["sha256"]
    suites = list(ET.parse(audit / "tests003.xml").getroot().iter("testsuite"))
    assert suites and all(
        int(s.attrib[k]) == 0 for s in suites for k in ("failures", "errors", "skipped")
    )
    timing, stages = {}, {}
    for side in ("serial", "parallel"):
        timing[side] = read(root / side / "attempt/supervisor.json")
        assert timing[side]["returncode"] == 0 and timing[side]["status"] == "exited"
        assert timing[side]["worker"]["status"] == "complete"
        assert not timing[side]["worker"]["resumed"]
        assert all(read(root / side / "isolation.json")["checks"].values())
        rows = [
            json.loads(line)
            for line in (root / side / "attempt/worker.log").read_text().splitlines()
        ]
        stages[side] = {r["stage"]: r["seconds"] for r in rows if r.get("event") == "stage"}
    totals = {side: t["process_seconds"] for side, t in timing.items()}
    summary = dict(
        exact_owned_science_and_artifacts=True,
        process_seconds=totals,
        observed_ratio=totals["serial"] / totals["parallel"],
        observed_reduction_percent=100 * (1 - totals["parallel"] / totals["serial"]),
        stages=stages,
        mapped_historical_sections=15,
        total_historical_sections=17,
        tests=sum(int(s.attrib["tests"]) for s in suites),
        tests_sha256=digest(audit / "tests003.xml"),
        full_historical_equivalence=False,
        dataset_wide_qualification=False,
        production_modified=False,
        qualified_cumulative_speedup=None,
        timing_scope=plan["scope"],
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for source, name in (
        (root / "plan.json", "plan.json"),
        (root / "comparison.json", "comparison.json"),
        (root / "resource-observations.jsonl", "resource-observations.jsonl"),
        (audit / "comparison.json", "historical-before-restoration.json"),
        (audit / "comparison002.json", "historical-comparison.json"),
        (audit / "tests003.xml", "tests.xml"),
    ):
        (out / name).write_bytes(source.read_bytes())
    table = ["| Stage | Serial folds (s) | Concurrent folds (s) |", "| --- | ---: | ---: |"]
    for stage in stages["serial"]:
        table.append(
            f"| {stage} | {stages['serial'][stage]:.3f} | {stages['parallel'][stage]:.3f} |"
        )
    (out / "stage-timings.md").write_text("\n".join(table) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5.5))
    first = read(repo / "reports/2026_11_05_algo07v3_predictive_parallel/summary.json")
    for offset, side, color in ((-0.18, "serial", "#888888"), (0.18, "parallel", "#3465a4")):
        bars = ax.bar(
            [offset, 1 + offset],
            [first["process_seconds"][side], totals[side]],
            width=0.36,
            label=side,
            color=color,
        )
        ax.bar_label(bars, fmt="%.1f s", padding=3)
    ax.set(
        xticks=[0, 1],
        xticklabels=[
            "First pair: serial then parallel\nHigher candidate load",
            "Repeat: parallel then serial\nShared host; no exclusive reservation",
        ],
        ylabel="Native GLRT ready → publication and supervisor completion (s)",
        ylim=(0, 530),
    )
    ax.legend()
    ax.set_title("DS26-0002 · exact scientific outputs and PNGs in both pairs")
    fig.text(
        0.5,
        0.035,
        "Repeat: 9.2% less elapsed time. One scan; "
        "cumulative and dataset-wide speedup unqualified.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.savefig(out / "runtime.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--audit", required=True, type=Path)
    args = parser.parse_args()
    render(args.root, args.audit)
