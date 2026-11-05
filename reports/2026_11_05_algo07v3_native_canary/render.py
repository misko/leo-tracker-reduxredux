"""Bind the completed baseline, diagnostic sample and current variance experiment."""

import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main(pair, variance):
    out = Path(__file__).resolve().parent
    plan = read(pair / "plan.json")
    for path, digest in plan["bindings"].items():
        assert sha(path) == digest, path
    clock = read(pair / "baseline/attempt/supervisor.json")
    assert clock["returncode"] == 0 and clock["status"] == "exited"
    assert clock["worker"]["status"] == "complete" and not clock["worker"]["resumed"]
    assert all(read(pair / "baseline/isolation.json")["checks"].values())
    comparison = read(pair / "comparison.json")
    assert comparison["exact_owned_science_and_artifacts"] and comparison["both_c_arms"]
    assert comparison["source_changes"] == sorted(plan["changed_modules"])
    assert comparison["added_modules"] == []
    for path, digest in comparison["input_bindings"].items():
        assert sha(path) == digest
    candidate_clock = read(pair / "candidate/attempt/supervisor.json")
    assert candidate_clock["status"] == "exited" and candidate_clock["returncode"] == 0
    assert candidate_clock["worker"]["status"] == "complete"
    assert not candidate_clock["worker"]["resumed"]
    assert all(read(pair / "candidate/isolation.json")["checks"].values())
    rows = [json.loads(s) for s in (pair / "baseline/attempt/worker.log").read_text().splitlines()]
    stages = {r["stage"]: r["seconds"] for r in rows if r.get("event") == "stage"}
    profile = read(pair / "baseline-sampling.json")
    sampling_log = (pair.parent / "baseline-sampling.log").read_text()
    match = re.search(r"Samples: (\d+) Errors: (\d+)", sampling_log)
    assert match
    samples, errors = map(int, match.groups())
    assert samples == sum(len(p["samples"]) for p in profile["profiles"])
    assert all(p["unit"] == "seconds" for p in profile["profiles"])
    frames, leaf, weight = profile["shared"]["frames"], Counter(), 0
    for thread in profile["profiles"]:
        for stack, value in zip(thread["samples"], thread["weights"], strict=True):
            if stack:
                f = frames[stack[-1]]
                leaf[(f["name"], Path(f.get("file", "")).name)] += value
                weight += value
    top = [dict(function=name, file=file, percent=100 * v / weight)
           for (name, file), v in leaf.most_common(8)]
    synthetic = read(variance / "synthetic-gated.json")
    assert all(r["exact"] for r in synthetic["records"])
    repo = out.parents[1]
    assert sha(repo / "tools/benchmark_algo07v3_variance.py") == synthetic["tool_sha256"]
    assert (sha(repo / "tools/probe_algo07v3_variance_groups.py")
            == synthetic["candidate_tool_sha256"])
    tests = list(ET.parse(variance / "tests-gated.xml").getroot().iter("testsuite"))
    assert sum(int(s.attrib["tests"]) for s in tests) == 24
    assert all(int(s.attrib[k]) == 0 for s in tests for k in ("errors", "failures", "skipped"))
    probe = read(variance / "probe.json")
    receipt = read(variance / "native/result.receipt.json")
    assert probe["complete"] and probe["exact"] and not probe["failures"]
    assert probe["calls"] == 6772
    assert probe["tool_sha256"] == synthetic["candidate_tool_sha256"]
    assert probe["reference_sha256"] == synthetic["reference_sha256"]
    assert probe["candidate_sha256"] == synthetic["candidate_sha256"]
    assert sha(repo / "tools/check_algo07v3_engine.py") == probe["engine_tool_sha256"]
    assert sha(variance / "native/result.json") == receipt["output_sha256"] == (
        "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    )
    candidate_rows = [json.loads(s)
                      for s in (pair / "candidate/attempt/worker.log").read_text().splitlines()]
    candidate_stages = {r["stage"]: r["seconds"] for r in candidate_rows
                        if r.get("event") == "stage"}
    assert list(candidate_stages) == list(stages)
    summary = dict(
        observed_utc=datetime.now(UTC).isoformat(), baseline_complete=True,
        baseline_native_process_seconds=clock["process_seconds"], baseline_stages=stages,
        baseline_selected_model=clock["worker"]["publication"]["selected_model"],
        baseline_arms=clock["worker"]["publication"]["arms"],
        candidate_native_process_seconds=candidate_clock["process_seconds"],
        candidate_stages=candidate_stages, pair_comparison_complete=True,
        exact_science_and_publication=True,
        observed_reduction_percent=100*(1-candidate_clock["process_seconds"]/clock["process_seconds"]),
        profile=dict(successful_samples=samples, reported_errors=errors, nonblocking=True,
                     duration_seconds=45, rate_hz=49, sampled_process_seconds=weight, top_leaf=top),
        synthetic_exact=True, variance_tests=24, variance_enabled_in_runtime=False,
        variance_native_exact=True, variance_native_calls=probe["calls"],
        variance_component_seconds=probe["component_seconds"],
        full_dataset_equivalence=False, cumulative_speedup=None, production_modified=False,
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for name, source in {
        "pair-plan.json": pair / "plan.json",
        "baseline-supervisor.json": pair / "baseline/attempt/supervisor.json",
        "baseline-isolation.json": pair / "baseline/isolation.json",
        "candidate-supervisor.json": pair / "candidate/attempt/supervisor.json",
        "candidate-isolation.json": pair / "candidate/isolation.json",
        "comparison.json": pair / "comparison.json",
        "baseline-sampling.json": pair / "baseline-sampling.json",
        "sampling.log": pair.parent / "baseline-sampling.log",
        "synthetic-ungated.json": variance / "synthetic.json",
        "synthetic-gated.json": variance / "synthetic-gated.json",
        "tests.xml": variance / "tests-gated.xml",
        "variance-probe.json": variance / "probe.json",
        "variance-native-receipt.json": variance / "native/result.receipt.json",
    }.items():
        (out / name).write_bytes(source.read_bytes())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    names = sorted(stages, key=stages.get, reverse=True)[:6][::-1]
    axes[0].barh(names, [stages[n] for n in names], color="#3465a4")
    axes[0].set(title="DS26-0066 · baseline largest stages", xlabel="Observed wall seconds")
    shown = top[:6][::-1]
    axes[1].barh([r["function"] for r in shown], [r["percent"] for r in shown], color="#6a5090")
    axes[1].set(title="45-second sampling window · leaf frames",
                xlabel="Share of sampled weight (%)")
    fig.text(0.5, 0.025, "Baseline only · sampled run is not a clean benchmark · "
             f"{errors} sampling errors · complete pair exact", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(out / "baseline-bottleneck.png", dpi=160)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(9, 5))
    bars = ax.bar(["Pre-optimization baseline", "Integrated solver"],
                  [clock["process_seconds"], candidate_clock["process_seconds"]],
                  color=["#888888", "#3465a4"])
    ax.bar_label(bars, fmt="%.1f s", padding=3)
    ax.set(title="DS26-0066 · exact native science and publication",
           ylabel="Native GLRT ready → supervisor exit (seconds)", ylim=(0, 1050))
    fig.text(.5, .025, "Observed 15.46% reduction · shared host · baseline sampled · "
             "not a cumulative speed claim",
             ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(out / "pair-runtime.png", dpi=160)
    plt.close(fig)
    omitted = ("baseline_stages", "candidate_stages", "baseline_arms", "profile")
    print(json.dumps({k: v for k, v in summary.items() if k not in omitted}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pair", type=Path, required=True)
    parser.add_argument("--variance", type=Path, required=True)
    args = parser.parse_args()
    main(args.pair, args.variance)
