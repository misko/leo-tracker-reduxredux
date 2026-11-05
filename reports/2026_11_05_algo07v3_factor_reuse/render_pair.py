"""Record completed exact runs and the independently mapped historical counters."""

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
    pair = root / "paired"
    plan = read(pair / "plan.json")
    for path, digest in plan["source_hashes"].items():
        assert sha(repo / path) == digest, path
    for name in ("comparison.json", "prior-comparison.json"):
        value = read(pair / name)
        assert value["exact_owned_science_and_artifacts"] and value["both_c_arms"]
        assert value["source_changes"] == plan["comparison_changed_modules"]
        assert value["added_modules"] == plan["comparison_added_modules"]
        for path, digest in value["input_bindings"].items():
            assert sha(Path(path)) == digest, path
    clocks, stages = {}, {}
    for side in ("baseline", "candidate"):
        assert sha(pair / f"{side}-kernel.py") == plan["kernel_hashes"][side]
        assert sha(pair / f"{side}-request.json") == plan["request_hashes"][side]
        clocks[side] = read(pair / side / "attempt/supervisor.json")
        assert clocks[side]["status"] == "exited" and clocks[side]["returncode"] == 0
        assert clocks[side]["worker"]["status"] == "complete"
        assert not clocks[side]["worker"]["resumed"]
        assert all(read(pair / side / "isolation.json")["checks"].values())
        lines = [
            json.loads(line)
            for line in (pair / side / "attempt/worker.log").read_text().splitlines()
        ]
        stages[side] = {r["stage"]: r["seconds"] for r in lines if r.get("event") == "stage"}
    audit = read(root / "historical-comparison005.json")
    assert audit["all_checked_values_exact"] and not audit["errors"]
    assert len(audit["mapped_policies"]) == 17 and not audit["missing_audit_mappings"]
    for binding in audit["input_bindings"].values():
        assert "sha256:" + sha(Path(binding["path"])) == binding["sha256"]
    oracle_path = root / "context-count-oracle002.json"
    assert (
        sha(oracle_path)
        == audit["mapped_policies"]["numerical_recovery"]["context_count_oracle_sha256"]
    )
    oracle = read(oracle_path)
    for binding in [oracle["tool"], *oracle["modules"].values()]:
        assert sha(Path(binding["path"])) == binding["sha256"]
    for relative, digest in oracle["inputs"].items():
        assert sha(Path(oracle["source"]) / relative) == digest
    tests = 0
    for name in ("tests002.xml", "upper-tests.xml"):
        suites = list(ET.parse(root / name).getroot().iter("testsuite"))
        assert suites and all(
            int(s.attrib[k]) == 0 for s in suites for k in ("failures", "errors", "skipped")
        )
        tests += sum(int(s.attrib["tests"]) for s in suites)
    times = {s: r["process_seconds"] for s, r in clocks.items()}
    summary = dict(
        exact_complete_pair=True,
        exact_prior_native_comparison=True,
        complete_process_seconds=times,
        observed_ratio=times["baseline"] / times["candidate"],
        observed_reduction_percent=100 * (1 - times["candidate"] / times["baseline"]),
        attribution="Unresolved: baseline experienced much greater CPU pressure",
        qualified_speedup=None,
        enabled_in_runtime=False,
        production_modified=False,
        historical_sections=17,
        full_historical_equivalence=False,
        dataset_wide_equivalence=False,
        tests=tests,
        stages=stages,
        next_experiment="Upper-root direct solve: 32 synthetic cases exact; native probe ongoing",
    )
    (out / "paired-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    copies = {
        "paired-comparison.json": pair / "comparison.json",
        "prior-native-comparison.json": pair / "prior-comparison.json",
        "paired-resources.jsonl": pair / "resource-observations.jsonl",
        "historical-17.json": root / "historical-comparison005.json",
        "historical-before-count-mapping.json": root / "historical-comparison004.json",
        "context-count-oracle.json": oracle_path,
        "tests-final.xml": root / "tests002.xml",
        "upper-tests.xml": root / "upper-tests.xml",
        "upper-synthetic.json": root / "upper-triangular-probe.json",
    }
    for name, source in copies.items():
        (out / name).write_bytes(source.read_bytes())
    rows = ["| Stage | Baseline (s) | Candidate (s) |", "| --- | ---: | ---: |"]
    for stage in stages["baseline"]:
        rows.append(
            f"| {stage} | {stages['baseline'][stage]:.3f} | {stages['candidate'][stage]:.3f} |"
        )
    (out / "paired-stages.md").write_text("\n".join(rows) + "\n")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bars = ax.bar(
        [
            "Baseline\nInitial CPU pressure avg10: 18.54%",
            "Factor reuse\nInitial CPU pressure avg10: 0.28%",
        ],
        list(times.values()),
        color=["#888888", "#3465a4"],
    )
    ax.bar_label(bars, fmt="%.1f s", padding=3)
    ax.set(
        ylabel="Native GLRT ready → publication and supervisor exit (s)",
        ylim=(0, 440),
        title="Exact complete outputs · unequal host load",
    )
    fig.text(
        0.5,
        0.025,
        "The total difference cannot be attributed to the 2.33% kernel saving. "
        "Candidate stays external.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "paired-runtime.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    render(parser.parse_args().root)
