"""Verify the complete exact-call experiment; do not infer pipeline speedup."""

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
    probe = read(root / "probe.json")
    receipt = read(root / "native/result.receipt.json")
    assert probe["complete"] and probe["exact"] and not probe["failures"]
    assert probe["calls"] == 6772
    expected = "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    assert sha(root / "native/result.json") == receipt["output_sha256"] == expected
    assert sha(repo / "tools/probe_algo07v3_factor_reuse.py") == probe["tool_sha256"]
    assert sha(repo / "tools/check_algo07v3_engine.py") == probe["engine_tool_sha256"]
    for path, digest in receipt["inputs"].items():
        assert sha(Path(path)) == digest, path
    for binding in receipt["modules"].values():
        assert sha(Path(binding["path"])) == binding["sha256"], binding["path"]
    products = read(root / "native/result.json")["presentation"]["products"]
    assert len(products) == 8
    for name, digest in products.items():
        assert sha(root / "native" / (name + ".png")) == digest
    audit = read(root / "historical-comparison003.json")
    assert audit["all_checked_values_exact"] and not audit["errors"]
    assert len(audit["mapped_policies"]) == 16
    assert audit["missing_audit_mappings"] == ["numerical_recovery"]
    for binding in audit["input_bindings"].values():
        assert "sha256:" + sha(Path(binding["path"])) == binding["sha256"]
    names, test_reports = set(), {}
    for name in ("tests.xml", "comparator-tests.xml"):
        tree = ET.parse(root / name).getroot()
        suites = list(tree.iter("testsuite"))
        assert suites and all(
            int(s.attrib[k]) == 0 for s in suites for k in ("failures", "errors", "skipped")
        )
        names.update((t.attrib["classname"], t.attrib["name"]) for t in tree.iter("testcase"))
        test_reports[name] = dict(
            tests=sum(int(s.attrib["tests"]) for s in suites), sha256=sha(root / name)
        )
    seconds = probe["component_seconds"]
    summary = dict(
        exact_calls=probe["calls"],
        exact_native_snapshot=expected,
        component_seconds=seconds,
        component_reduction_percent=100 * (1 - seconds["candidate"] / seconds["reference"]),
        diagnostic_process_seconds=probe["process_seconds"],
        tests=test_reports,
        distinct_test_cases=len(names),
        historical_sections=16,
        remaining_historical_sections=["numerical_recovery"],
        full_historical_equivalence=False,
        dataset_wide_equivalence=False,
        qualified_pipeline_speedup=None,
        enabled_in_runtime=False,
        production_modified=False,
        complete_pair_plan=str(root / "paired/plan.json"),
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for source, name in (
        (root / "probe.json", "probe.json"),
        (root / "native/result.receipt.json", "native-receipt.json"),
        (root / "historical-comparison.json", "historical-before-metadata-mapping.json"),
        (root / "historical-comparison003.json", "historical-comparison.json"),
        (root / "tests.xml", "tests.xml"),
        (root / "comparator-tests.xml", "comparator-tests.xml"),
        (root / "paired/plan.json", "paired-plan.json"),
    ):
        (out / name).write_bytes(source.read_bytes())

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(8, 5))
    bars = ax.bar(
        ["Current owned kernel", "Separate-RHS factor reuse"],
        list(seconds.values()),
        color=["#888888", "#3465a4"],
    )
    ax.bar_label(bars, fmt="%.3f s", padding=3)
    ax.set(
        ylabel="Summed likelihood time (s)",
        ylim=(0, 195),
        title="DS26-0002 · 6,772 exact paired likelihood calls",
    )
    fig.text(
        0.5,
        0.025,
        "2.33% component saving. Both kernels run in the probe; no pipeline speedup claim.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.065, 1, 1))
    fig.savefig(out / "component-runtime.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    render(parser.parse_args().root)
