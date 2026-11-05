"""Publish the completed bounded-variance pair without upgrading timing claims."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root, boundaries, report_name):
    plan = read(root / "plan.json")
    comparison = read(root / "comparison.json")
    for bindings in (plan["bindings"], comparison["input_bindings"]):
        for name, digest in bindings.items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    assert comparison["exact_owned_science_and_artifacts"] and comparison["both_c_arms"]
    assert comparison["source_changes"] == ["leo.analysis.localization_v3.hierarchical"]
    assert comparison["added_modules"] == []
    tests = list(ET.parse(boundaries).getroot().iter("testsuite"))
    assert sum(int(s.attrib["tests"]) for s in tests) == 9
    assert all(int(s.attrib[k]) == 0 for s in tests for k in ("failures", "errors", "skipped"))
    times, stages, clocks = {}, {}, {}
    for arm in ("baseline", "candidate"):
        clock = read(root / arm / "attempt/supervisor.json")
        assert clock["status"] == "exited" and clock["returncode"] == 0
        assert clock["worker"]["status"] == "complete" and not clock["worker"]["resumed"]
        assert all(read(root / arm / "isolation.json")["checks"].values())
        clocks[arm] = clock
        times[arm] = clock["process_seconds"]
        rows = [json.loads(s) for s in (root / arm / "attempt/worker.log").read_text().splitlines()]
        stages[arm] = {r["stage"]: r["seconds"] for r in rows if r.get("event") == "stage"}
    assert list(stages["baseline"]) == list(stages["candidate"])
    if not report_name or Path(report_name).name != report_name or report_name in (".", ".."):
        raise ValueError("A single fresh report-directory name is required")
    out = Path(__file__).resolve().parent / report_name
    out.mkdir(exist_ok=False)
    for name in ("plan.json", "comparison.json"):
        (out / name).write_bytes((root / name).read_bytes())
    (out / "boundary-tests.xml").write_bytes(boundaries.read_bytes())
    for arm in times:
        for name, source in {
            f"{arm}-supervisor.json": root / arm / "attempt/supervisor.json",
            f"{arm}-isolation.json": root / arm / "isolation.json",
            f"{arm}-resources-start.json": root / f"{arm}-resources-start.json",
            f"{arm}-resources-end.json": root / f"{arm}-resources-end.json",
        }.items():
            (out / name).write_bytes(source.read_bytes())
    reduction = 100 * (1 - times["candidate"] / times["baseline"])
    direction = (f"{reduction:.2f}% faster" if reduction >= 0 else f"{-reduction:.2f}% slower")
    summary = dict(exact=True, seconds=times, stages=stages,
                   observed_reduction_percent=reduction, qualified_speedup=None,
                   production_modified=False, enabled_in_runtime=False,
                   full_dataset_equivalence=False, boundary_tests=9)
    cpu = {}
    for arm in times:
        path = root / f"{arm}-process-time.txt"
        if path.exists():
            (out / path.name).write_bytes(path.read_bytes())
            values = dict(line.strip().rsplit(": ", 1) for line in path.read_text().splitlines()
                          if ": " in line)
            assert values["Exit status"] == "0"
            cpu[arm] = dict(user_seconds=float(values["User time (seconds)"]),
                            system_seconds=float(values["System time (seconds)"]),
                            maximum_rss_kbytes=int(values["Maximum resident set size (kbytes)"]))
    assert not cpu or set(cpu) == set(times)
    summary["process_cpu_accounting"] = cpu
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
    colors = ["#888888", "#3465a4"]
    bars = axes[0].bar(["Integrated baseline", "Variance batching"], list(times.values()),
                       color=colors)
    axes[0].bar_label(bars, fmt="%.1f s", padding=3)
    axes[0].set(ylabel="Native GLRT ready → supervisor exit (s)",
                title="DS26-0002 · complete path", ylim=(0, max(times.values()) * 1.15))
    labels = sorted(stages["baseline"], key=stages["baseline"].get, reverse=True)[:6][::-1]
    y = np.arange(len(labels))
    for i, arm in enumerate(times):
        axes[1].barh(y + (i - .5) * .36, [stages[arm][k] for k in labels],
                     height=.36, color=colors[i], label=arm)
    axes[1].set(yticks=y, yticklabels=labels, xlabel="Observed wall seconds",
                title="Largest baseline stages")
    axes[1].legend()
    fig.text(.5, .025, "Exact science, both arms and eight PNGs · shared host · "
             "not a cumulative speed claim", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, 1))
    fig.savefig(out / "runtime.png", dpi=160)
    plt.close(fig)
    table = "\n".join(f"| {name} | {stages['baseline'][name]:.3f} | "
                      f"{stages['candidate'][name]:.3f} |" for name in stages["baseline"])
    first = plan["sequence"][0]
    runner = "run_variance_cpu_pair.py" if cpu else "run_variance_pair.py"
    cpu_table = ""
    if cpu:
        cpu_table = ("\n| GNU time accounting | User CPU s | System CPU s | Max RSS KiB |\n"
                     "| --- | ---: | ---: | ---: |\n" + "\n".join(
                         f"| {arm} | {r['user_seconds']:.2f} | {r['system_seconds']:.2f} | "
                         f"{r['maximum_rss_kbytes']} |" for arm, r in cpu.items()) + "\n\n"
                     "CPU time includes waited-for children. It is separate from wall latency; "
                     "host frequency and memory contention can still affect it.\n")
    report = f"""# Bounded variance batching: complete standalone comparison

2026-11-05. External development prototype; no deployment or runtime integration.

The candidate and integrated standalone baseline match **exactly** on DS26-0002:
both calibration arms, all science and audits, all eight PNG bytes, diagnostic
grid/path data and published result fields. Only the declared hierarchical
module differs. This is owned-engine equivalence, not full historical ALGO07
or dataset-wide qualification. [Comparison](comparison.json).

| Native GLRT ready through publication and supervisor exit | Observed seconds |
| --- | ---: |
| Integrated baseline | {times['baseline']:.3f} |
| Bounded variance batching | {times['candidate']:.3f} |

The candidate was **{direction}** in this pair. The {first} ran first; both used
CPUs 0–2, one BLAS thread, identical numerical budgets and a 1,200-second outer
limit. These shared-host timings do not establish a controlled population or
cumulative speedup. Resource observations are preserved alongside the receipts.
One pair does not establish performance qualification. Compare it with the
preceding pair and the alternating exact-call timings, retaining regressions.
Do not attribute changes in unchanged stages to variance batching.
{cpu_table}

![Complete path and stage observations](runtime.png)

The prototype groups independent equal-width variance products and reductions,
preserving each group's arithmetic and restoring group order before updating
precision. Batches above 1 MiB per stacked matrix tensor and singleton groups
use the original reductions. No observations, priors or iterations are removed.

The preceding native probe compared all 6,772 calls exactly and measured an
11.17% kernel reduction. Nine additional tests now cover the exact batch-memory
boundary, strided arrays, unequal feature scales, noncontiguous group labels,
mixed singleton/empty groups and short iteration budgets. All pass.
[Boundary tests](boundary-tests.xml), [preceding evidence](../README.md).

| Stage | Baseline seconds | Candidate seconds |
| --- | ---: | ---: |
{table}

Next: resolve the complete-path timing regression and extend this candidate
through the larger native guarded-reassociation case before integration.
Full DS26 retains 159 fast members, 158 available
inputs and one unavailable member. Ordinary admission, full historical
metadata qualification and the cumulative tenfold target remain open.

Reproduce with [pair runner](../{runner}) and
[renderer](../render_variance_pair.py); immutable inputs and sources are recorded
in [plan](plan.json). Raw evidence: `{root}`.
"""
    (out / "README.md").write_text(report)
    print(json.dumps({k: v for k, v in summary.items() if k != "stages"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--boundary-tests", type=Path, required=True)
    parser.add_argument("--name", default="variance-pair")
    args = parser.parse_args()
    main(args.root, args.boundary_tests, args.name)
