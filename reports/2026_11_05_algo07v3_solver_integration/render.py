"""Verify the exact Gaussian probe and the integrated isolated CLI result."""

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def render(root, gaussian):
    out = Path(__file__).resolve().parent
    plan = read(root / "plan.json")
    for path, digest in plan["source_bindings"].items():
        assert sha(path) == digest, path
    comparison = read(root / "comparison.json")
    assert comparison["exact_owned_science_and_artifacts"] and comparison["both_c_arms"]
    assert comparison["source_changes"] == sorted(plan["changed_modules"])
    assert comparison["added_modules"] == []
    for path, digest in comparison["input_bindings"].items():
        assert sha(path) == digest, path
    clock = read(root / "cli/attempt/supervisor.json")
    assert clock["status"] == "exited" and clock["returncode"] == 0
    assert clock["worker"]["status"] == "complete" and not clock["worker"]["resumed"]
    assert all(read(root / "cli/isolation.json")["checks"].values())
    probe = read(gaussian / "probe.json")
    receipt = read(gaussian / "native/result.receipt.json")
    assert probe["complete"] and probe["exact"]
    assert sha(gaussian / "native/result.json") == receipt["output_sha256"] == (
        "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    )
    # The external probe now uses frozen methods so it remains runnable after
    # integration. Bind the original executed driver to its published commit.
    driver = subprocess.check_output([
        "git", "show", "dc8b33922:tools/probe_algo07v3_discarded_gaussian.py"
    ])
    assert hashlib.sha256(driver).hexdigest() == probe["tool_sha256"]
    assert sha(receipt["tool"]["path"]) == receipt["tool"]["sha256"]
    for path, digest in receipt["inputs"].items():
        assert sha(path) == digest
    for name, row in receipt["modules"].items():
        path = Path(row["path"])
        if name in plan["changed_modules"]:
            path = root / ("baseline-" + name.rsplit(".", 1)[-1] + ".py")
        assert sha(path) == row["sha256"], name
    assert {k: v["calls"] for k, v in probe["calculations"].items()} == {
        "NormalPosition": 1676, "DiscoveryPosition": 16,
    }
    assert all(not r["failures"] for r in probe["calculations"].values())
    suites = list(ET.parse(root / "tests.xml").getroot().iter("testsuite"))
    assert all(int(s.attrib[k]) == 0 for s in suites for k in ("errors", "failures", "skipped"))
    count = sum(int(s.attrib["tests"]) for s in suites)
    assert count == 820
    lines = [
        json.loads(line)
        for line in (root / "cli/attempt/worker.log").read_text().splitlines()
    ]
    stages = {r["stage"]: r["seconds"] for r in lines if r.get("event") == "stage"}
    old = sum(r["seconds"]["reference"] for r in probe["calculations"].values())
    new = sum(r["seconds"]["candidate"] for r in probe["calculations"].values())
    summary = dict(
        integrated_in_development=True, deployed=False, tests=count,
        gaussian_exact_calls=1692, gaussian_component_seconds=dict(reference=old, candidate=new),
        gaussian_component_saving_seconds=old-new,
        native_process_seconds=clock["process_seconds"], stages=stages,
        exact_both_arms_science_and_artifacts=True,
        cumulative_speedup=None, qualified_speedup=None, full_ds26_equivalence=False,
        admission="validation-all-work; ordinary production timing policy remains unqualified",
    )
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    for name, source in {
        "comparison.json": root / "comparison.json", "plan.json": root / "plan.json",
        "tests.xml": root / "tests.xml", "gaussian-probe.json": gaussian / "probe.json",
        "gaussian-native-receipt.json": gaussian / "native/result.receipt.json",
        "frozen-oracles.json": root / "frozen-oracles.json",
    }.items():
        (out / name).write_bytes(source.read_bytes())
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 5))
    names = sorted(stages, key=stages.get, reverse=True)[:7]
    ax.barh(names[::-1], [stages[n] for n in names[::-1]], color="#3465a4")
    ax.set(xlabel="Observed wall-clock seconds", title="Integrated ALGO07v3 · largest stages")
    fig.text(
        0.5, 0.025,
        "DS26-0002 · exact science/publication · shared host; not a matched speed benchmark",
        ha="center", fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.savefig(out / "stages.png", dpi=160)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != "stages"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--gaussian", required=True, type=Path)
    args = parser.parse_args()
    render(args.root, args.gaussian)
