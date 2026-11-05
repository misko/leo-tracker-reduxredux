"""Verify and render the completed external family concurrency experiment."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def main(root):
    plan, probe, comparison = (read(root / f"{name}.json")
                               for name in ("plan", "probe", "comparison"))
    for name, sha in plan["bindings"].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    assert probe["complete"] and probe["exact"] and comparison["exact"]
    assert len(probe["comparisons"]) == 1 and probe["comparisons"][0]["exact"]
    assert comparison["scientific_snapshot_exact"]
    assert len(comparison["figures"]) == 8 and all(comparison["figures"].values())
    assert comparison["actual_sha256"] == comparison["expected_sha256"] == (
        "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68")
    assert all(p["arms"] == ["c0", "fitted_c"] for p in probe["pairs"])
    out = Path(__file__).resolve().parent
    suites = list(ET.parse(out / "tests.xml").getroot().iter("testsuite"))
    assert sum(int(s.attrib["tests"]) for s in suites) == 3
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped"))
    for name in ("probe.json", "comparison.json", "resources-start.json", "resources-end.json"):
        (out / name).write_bytes((root / name).read_bytes())
    (out / "native-receipt.json").write_bytes((root / "native/result.receipt.json").read_bytes())
    clocks = probe["comparisons"][0]["clocks"]
    wall = {k: r["seconds"] for k, r in clocks.items()}
    cpu = {k: r["parent_cpu_seconds"] + r["children_cpu_seconds"] for k, r in clocks.items()}
    reduction = 100 * (1 - wall["candidate"] / wall["reference"])
    summary = dict(native_exact=True, pngs_exact=8, tests=3,
                   family_wall_seconds=wall, family_cpu_seconds=cpu,
                   family_observed_reduction_percent=reduction,
                   parallel_pairs=len(probe["pairs"]),
                   diagnostic_process_seconds=probe["process_seconds"],
                   enabled_in_runtime=False, publication_qualified=False,
                   qualified_pipeline_speedup=None, production_modified=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 5))
    titles = ("Family stage wall time", "Parent + child CPU")
    for ax, values, title in zip(axes, (wall, cpu), titles, strict=True):
        bars = ax.bar(["Serial reference", "Concurrent arms"], list(values.values()),
                       color=["#888888", "#3465a4"])
        ax.bar_label(bars, fmt="%.2f s", padding=3)
        ax.set(title=title, ylabel="Seconds", ylim=(0, max(values.values()) * 1.2))
    fig.suptitle("DS26-0002 · exact family policy and native scientific/PNG snapshot")
    fig.text(.5, .025, "External diagnostic runs both methods · shared host · "
             "not a whole-pipeline latency measurement", ha="center", fontsize=9)
    fig.tight_layout(rect=(0, .07, 1, .95))
    fig.savefig(out / "family-runtime.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    main(args.root)
