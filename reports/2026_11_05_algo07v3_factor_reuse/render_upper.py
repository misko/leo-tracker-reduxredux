"""Verify and summarize the external upper-root exactness and complete-path pair."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render(root):
    out = Path(__file__).resolve().parent
    probe = read(root / "probe.json")
    receipt = read(root / "native/result.receipt.json")
    driver = read(root / "probe.driver.json")
    assert probe["complete"] and probe["exact"] and not probe["failures"]
    assert probe["calls"] == 6772
    suites = list(ET.parse(root / "upper-tests.xml").getroot().iter("testsuite"))
    assert sum(int(s.attrib["tests"]) for s in suites) == 14
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped"))
    for path, digest in driver["files"].items():
        assert sha(path) == digest, path
    assert sha(root / "native/result.json") == receipt["output_sha256"] == (
        "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    )
    pair = root / "paired"
    plan = read(pair / "plan.json")
    assert plan["sequence"] == ["candidate", "baseline"]
    for path, digest in plan["bindings"].items():
        assert sha(path) == digest, path
    comparison = read(pair / "comparison.json")
    assert comparison["exact_owned_science_and_artifacts"] and comparison["both_c_arms"]
    assert comparison["source_changes"] == ["leo.analysis.localization_v3.hierarchical"]
    assert comparison["added_modules"] == []
    for path, digest in comparison["input_bindings"].items():
        assert sha(path) == digest, path
    clocks, stages = {}, {}
    for side in ("baseline", "candidate"):
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
    assert list(stages["baseline"]) == list(stages["candidate"])
    resources = [json.loads(line) for line in (pair / "resources.jsonl").read_text().splitlines()]
    pressure = {}
    for side in clocks:
        rows = [r for r in resources if r["arm"] == side]
        assert rows[0]["event"] == "start" and rows[-1]["event"] == "end"
        averages = [float(r["cpu_pressure"].split("avg10=")[1].split()[0]) for r in rows]
        totals = [int(r["cpu_pressure"].splitlines()[0].split("total=")[1]) for r in rows]
        pressure[side] = dict(initial_avg10=averages[0], maximum_avg10=max(averages),
                              stalled_seconds=(totals[-1] - totals[0]) / 1e6,
                              start_load=rows[0]["load"], end_load=rows[-1]["load"])
    seconds = {s: c["process_seconds"] for s, c in clocks.items()}
    component = probe["component_seconds"]
    summary = dict(
        exact_calls=probe["calls"], exact_native_snapshot=True, exact_complete_pair=True,
        complete_process_seconds=seconds, component_seconds=component,
        component_reduction_percent=100 * (1 - component["candidate"] / component["reference"]),
        observed_process_reduction_percent=100 * (1 - seconds["candidate"] / seconds["baseline"]),
        observed_process_ratio=seconds["baseline"] / seconds["candidate"],
        host_pressure=pressure, stages=stages, qualified_speedup=None,
        dataset_wide_equivalence=False, enabled_in_runtime=False, production_modified=False,
        scope="Native GLRT ready through scientific storage and atomic publication",
        excluded="Capture, queue delay and GLRT extraction; cumulative legacy-to-v3 speedup",
    )
    (out / "upper-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for name, source in {
        "upper-probe.json": root / "probe.json",
        "upper-native-receipt.json": root / "native/result.receipt.json",
        "upper-driver.json": root / "probe.driver.json",
        "upper-plan.json": pair / "plan.json",
        "upper-comparison.json": pair / "comparison.json",
        "upper-resources.jsonl": pair / "resources.jsonl",
        "upper-expanded-tests.xml": root / "upper-tests.xml",
    }.items():
        (out / name).write_bytes(source.read_bytes())
    table = ["| Stage | Baseline (s) | Upper-root candidate (s) |", "| --- | ---: | ---: |"]
    table += [
        f"| {s} | {stages['baseline'][s]:.3f} | {stages['candidate'][s]:.3f} |"
        for s in stages["baseline"]
    ]
    (out / "upper-stages.md").write_text("\n".join(table) + "\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.8))
    titles = (
        "Likelihood kernel · alternating exact-call probe",
        "Complete pipeline · candidate ran first",
    )
    for ax, values, title in zip(axes, (component, seconds), titles, strict=True):
        bars = ax.bar(
            ["Baseline", "Upper-root candidate"], list(values.values()),
            color=["#888888", "#3465a4"],
        )
        ax.bar_label(bars, fmt="%.1f s", padding=3)
        ax.set(ylabel="Elapsed seconds", title=title, ylim=(0, max(values.values()) * 1.17))
    fig.text(
        0.5, 0.025,
        "DS26-0002 · exact outputs · shared host · one complete-path pair; "
        "population and cumulative speedup unqualified",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "upper-runtime.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != "stages"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    render(parser.parse_args().root)
