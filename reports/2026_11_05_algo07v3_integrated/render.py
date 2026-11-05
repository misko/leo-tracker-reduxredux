"""Verify receipts and render the integrated-kernel timing observations."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def run(root):
    out = Path(__file__).resolve().parent
    sides = ("baseline", "optimized", "baseline2")
    timings = {s: read(root / s / "attempt/supervisor.json") for s in sides}
    for row in timings.values():
        assert row["status"] == "exited" and row["returncode"] == 0
        assert row["worker"]["status"] == "complete" and not row["worker"]["resumed"]
    comparisons = [read(root / n) for n in ("owned-comparison.json", "owned-comparison2.json")]
    for row in comparisons:
        assert row["exact_owned_science_and_artifacts"]
        assert row["source_changes"] == ["leo.analysis.localization_v3.hierarchical"]
        for name, sha in row["input_bindings"].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha
    historical = read(root / "historical-comparison.json")
    assert (
        historical["all_checked_values_exact"] and not historical["full_intermediate_equivalence"]
    )
    for binding in historical["input_bindings"].values():
        assert (
            "sha256:" + hashlib.sha256(Path(binding["path"]).read_bytes()).hexdigest()
            == binding["sha256"]
        )
    inventory = read(root / "ds26-input-inventory002.json")
    assert inventory["fast_members"] == 159
    assert inventory["counts"] == {"available": 158, "no_native_run": 1}
    tests = root / "tests-final.xml"
    suites = list(ET.parse(tests).getroot().iter("testsuite"))
    assert suites and all(
        int(s.attrib[k]) == 0 for s in suites for k in ("failures", "errors", "skipped")
    )
    plan = read(root / "plan002.json")
    for side in ("baseline", "optimized"):
        assert (
            hashlib.sha256((root / (side + "-kernel.py")).read_bytes()).hexdigest()
            == plan["kernel_sha256"][side]
        )
    assert (
        hashlib.sha256(
            (out.parents[1] / "src/leo/analysis/localization_v3/hierarchical.py").read_bytes()
        ).hexdigest()
        == plan["kernel_sha256"]["optimized"]
    )
    isolation = {s: read(root / s / "isolation.json") for s in sides}
    assert all(all(r["checks"].values()) for r in isolation.values())
    stages = {}
    for side in sides:
        rows = [
            json.loads(line)
            for line in (root / side / "attempt/worker.log").read_text().splitlines()
        ]
        stages[side] = {r["stage"]: r["seconds"] for r in rows if r.get("event") == "stage"}
    assert all(list(rows) == list(stages["baseline"]) for rows in stages.values())
    seconds = {s: r["process_seconds"] for s, r in timings.items()}
    summary = dict(
        exact_science_and_publication=True,
        process_seconds=seconds,
        observed_first_pair_ratio=seconds["baseline"] / seconds["optimized"],
        observed_followup_pair_ratio=seconds["baseline2"] / seconds["optimized"],
        observed_followup_reduction_percent=100 * (1 - seconds["optimized"] / seconds["baseline2"]),
        qualified_speedup=None,
        timing_scope=(
            "Native GLRT ready through supervised worker outcome and all published artifacts"
        ),
        cpu=23,
        cpu_class="efficiency",
        shared_host=True,
        stages=stages,
        exclusive_tail_seconds={
            s: {
                "native_to_render": r["worker"]["native_to_render_seconds"],
                "evidence_projection_save": r["worker"]["evidence_save_seconds"],
                "publication": r["worker"]["publication_seconds"],
                "startup_and_final_supervision": r["process_seconds"] - r["worker"]["seconds"],
            }
            for s, r in timings.items()
        },
        historical_checks=len(historical["checks"]),
        historical_mapped_sections=len(historical["mapped_policies"]),
        remaining_historical_mappings=historical["missing_audit_mappings"],
        full_historical_equivalence=False,
        ds26_fast_members=159,
        ds26_available=158,
        ds26_unavailable=1,
        ds26_numerically_qualified=False,
        tests=sum(int(s.attrib["tests"]) for s in suites),
        tests_sha256=hashlib.sha256(tests.read_bytes()).hexdigest(),
        runtime_kernel_enabled=True,
        production_modified=False,
    )
    for name in (
        "owned-comparison.json",
        "owned-comparison2.json",
        "historical-comparison.json",
        "plan002.json",
        "hardware.json",
        "resource-observations.jsonl",
        "ds26-input-inventory.json",
        "ds26-input-inventory002.json",
    ):
        (out / name).write_bytes((root / name).read_bytes())
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    (out / "isolation.json").write_text(json.dumps(isolation, indent=2) + "\n")
    for side, row in timings.items():
        (out / (side + "-timing.json")).write_text(json.dumps(row, indent=2) + "\n")
    table = [
        "| Stage | First baseline (s) | Optimized (s) | Repeated baseline (s) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for stage in stages["baseline"]:
        table.append(f"| {stage} | " + " | ".join(f"{stages[s][stage]:.3f}" for s in sides) + " |")
    (out / "stage-timings.md").write_text("\n".join(table) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.4))
    fig.subplots_adjust(left=0.14, right=0.98, top=0.86, bottom=0.24, wspace=0.65)
    ax = axes[0]
    for i, side in enumerate(sides):
        value = seconds[side]
        ax.barh(i, value, color=["#aaaaaa", "#3465a4", "#777777"][i])
        ax.text(value, i, f" {value:.1f} s", va="center", fontsize=9)
    ax.set(
        yticks=[0, 1, 2],
        yticklabels=["Baseline · heavier load", "Optimized", "Baseline · repeat"],
        xlim=(0, max(seconds.values()) * 1.28),
        xlabel="Native input → publication (seconds)",
    )
    ax.invert_yaxis()
    ax.set_title("Same CPU 23; all outputs exact")
    ax = axes[1]
    ranked = sorted(stages["optimized"], key=stages["optimized"].get, reverse=True)[:8]
    ax.barh(range(len(ranked)), [stages["optimized"][s] for s in ranked], color="#3465a4")
    ax.set(
        yticks=range(len(ranked)),
        yticklabels=[s.replace("_", " ") for s in ranked],
        xlabel="Optimized stage wall time (seconds)",
    )
    ax.invert_yaxis()
    ax.set_title("Largest remaining stages")
    fig.suptitle("DS26-0002 · assembly optimization integrated into standalone ALGO07v3")
    fig.text(
        0.5,
        0.035,
        "Shared host, sequential runs; first baseline had substantially heavier load.\n"
        "These observations do not establish dataset-wide or tenfold speedup.",
        ha="center",
        fontsize=10,
    )
    fig.savefig(out / "runtime-observations.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k not in ("stages", "exclusive_tail_seconds")},
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    run(parser.parse_args().root)
