"""Verify fresh CLI receipts before reporting owned initial-fit concurrency."""

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
    plan = read(root / "plan003.json")
    for name, digest in plan["source_hashes"].items():
        assert sha(repo / name) == digest, name
    assert sha(root / "serial-job.py") == plan["baseline_job_sha256"]
    comparisons = {
        name: read(root / name) for name in ("prior-comparison.json", "comparison002.json")
    }
    for value in comparisons.values():
        assert value["exact_owned_science_and_artifacts"] and value["both_c_arms"]
        for path, digest in value["input_bindings"].items():
            assert sha(Path(path)) == digest
    assert comparisons["comparison002.json"]["source_changes"] == plan["comparison_changed_modules"]
    assert comparisons["comparison002.json"]["added_modules"] == plan["comparison_added_modules"]
    module_audit = read(root / "module-audit.json")
    assert module_audit["main_alias_matches"] and not module_audit["removed"]
    assert module_audit["added"]["__mp_main__"] == module_audit["main_binding"]
    timing, stages, isolation = {}, {}, {}
    for side in ("serial", "parallel"):
        timing[side] = read(root / side / "attempt/supervisor.json")
        row = timing[side]
        assert row["status"] == "exited" and row["returncode"] == 0
        assert row["worker"]["status"] == "complete" and not row["worker"]["resumed"]
        isolation[side] = read(root / side / "isolation.json")
        assert all(isolation[side]["checks"].values())
        log = [
            json.loads(line)
            for line in (root / side / "attempt/worker.log").read_text().splitlines()
        ]
        stages[side] = {r["stage"]: r["seconds"] for r in log if r.get("event") == "stage"}
    assert list(stages["serial"]) == list(stages["parallel"]) and len(stages["serial"]) == 20
    test_path = root / "tests002.xml"
    suites = list(ET.parse(test_path).getroot().iter("testsuite"))
    assert suites and all(
        int(s.attrib[k]) == 0 for s in suites for k in ("failures", "errors", "skipped")
    )
    totals = {s: row["process_seconds"] for s, row in timing.items()}
    summary = dict(
        exact_science_and_publication=True,
        both_calibration_arms=True,
        process_seconds=totals,
        observed_pair_ratio=totals["serial"] / totals["parallel"],
        observed_pair_reduction_percent=100 * (1 - totals["parallel"] / totals["serial"]),
        qualified_dataset_speedup=None,
        scope=(
            "Native GLRT ready through scientific storage, eight PNGs, "
            "atomic WebUI manifest and worker outcome"
        ),
        initial_stage_seconds={s: rows["initial"] for s, rows in stages.items()},
        stages=stages,
        tests=sum(int(s.attrib["tests"]) for s in suites),
        test_report_sha256=sha(test_path),
        default_owned_cli_concurrency_enabled=True,
        scientific_budgets_and_public_contracts_unchanged=True,
        dataset_wide_equivalence=False,
        production_modified=False,
        prior_serial_equivalence_verified=True,
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for name in (
        "plan003.json",
        "comparison002.json",
        "prior-comparison.json",
        "resource-observations.jsonl",
        "module-audit.json",
    ):
        (out / name).write_bytes((root / name).read_bytes())
    (out / "isolation.json").write_text(json.dumps(isolation, indent=2) + "\n")
    for side, value in timing.items():
        (out / (side + "-timing.json")).write_text(json.dumps(value, indent=2) + "\n")
    table = ["| Stage | Serial (s) | Parallel initial arms (s) |", "| --- | ---: | ---: |"]
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
        ["Serial", "Parallel initial arms"], list(totals.values()), color=["#888888", "#3465a4"]
    )
    axes[0].bar_label(bars, fmt="%.1f s", padding=3)
    axes[0].set(
        ylabel="Native input → publication and outcome (s)", ylim=(0, max(totals.values()) * 1.2)
    )
    largest = sorted(stages["parallel"], key=stages["parallel"].get, reverse=True)[:7]
    y = np.arange(len(largest))
    for delta, side, color in ((-0.2, "serial", "#888888"), (0.2, "parallel", "#3465a4")):
        axes[1].barh(
            y + delta, [stages[side][k] for k in largest], height=0.4, label=side, color=color
        )
    axes[1].set(
        yticks=y, yticklabels=[s.replace("_", " ") for s in largest], xlabel="Stage wall time (s)"
    )
    axes[1].invert_yaxis()
    axes[1].legend()
    fig.suptitle("DS26-0002 · owned concurrent initial fits · exact science and publication")
    fig.text(
        0.5,
        0.04,
        "One sequential pair on a shared host; same CPU allowance (0, 1), one BLAS thread.\n"
        "Includes eight PNGs and publication. Excludes capture, GLRT extraction and queue delay.\n"
        "This observation does not establish dataset-wide or tenfold speedup.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(out / "runtime.png", dpi=150)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != "stages"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    render(parser.parse_args().root)
