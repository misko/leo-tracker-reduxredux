"""Verify the full native assembly experiment and render component timings."""

import argparse
import hashlib
import json
import runpy
import xml.etree.ElementTree as ET
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root):
    out = Path(__file__).resolve().parent
    probe = json.loads((root / "probe.json").read_bytes())
    comparison = json.loads((root / "comparison002.json").read_bytes())
    native = root / "native/result.json"
    assert probe["complete"] and probe["exact"] and not probe["failures"]
    assert digest(native) == "4f7c74a132b415e9bd6e130dcbc0d7082fa72c822d53f76810f8a9fa13323d68"
    assert probe["tool_sha256"] == digest(out.parents[1] / "tools/probe_algo07v3_assembly.py")
    data = json.loads(native.read_bytes())
    for name, sha in data["presentation"]["products"].items():
        assert digest(root / "native" / (name + ".png")) == sha
    assert data["presentation"]["grid_complete"] and data["presentation"]["grid_points"] == 179
    assert (
        comparison["all_checked_values_exact"] and not comparison["full_intermediate_equivalence"]
    )
    for binding in comparison["input_bindings"].values():
        assert "sha256:" + digest(Path(binding["path"])) == binding["sha256"]
    factory = runpy.run_path(str(out.parent / "2026_11_05_algo07v3_pair/probe_assembly.py"))
    _, old, new = factory["candidate_function"]()
    assert hashlib.sha256(old.encode()).hexdigest() == probe["reference_sha256"]
    assert hashlib.sha256(new.encode()).hexdigest() == probe["candidate_sha256"]
    _, old, new = runpy.run_path(str(out / "probe_factor_reuse.py"))["candidate_function"]()
    factors = [
        json.loads((root / name).read_bytes())
        for name in (
            "factor-reuse.json",
            "factor-reuse002.json",
            "factor-reuse003.json",
        )
    ]
    for value in factors:
        assert value["exact"]
        assert hashlib.sha256(old.encode()).hexdigest() == value["reference_sha256"]
        assert hashlib.sha256(new.encode()).hexdigest() == value["candidate_sha256"]
    suites = list(ET.parse(root / "tests.xml").getroot().iter("testsuite"))
    assert suites and all(
        int(s.attrib[k]) == 0
        for s in suites
        for k in (
            "failures",
            "errors",
            "skipped",
        )
    )
    seconds = probe["component_seconds"]
    summary = dict(
        full_native_snapshot_sha256=digest(native),
        native_glrt_to_figures_exact=True,
        likelihood_calls=probe["calls"],
        shapes=len(probe["shapes"]),
        component_seconds=seconds,
        component_seconds_saved=seconds["reference"] - seconds["candidate"],
        component_time_reduction_percent=100 * (1 - seconds["candidate"] / seconds["reference"]),
        qualification_process_seconds=probe["process_seconds"],
        qualified_end_to_end_speedup=None,
        mapped_reference_sections=len(comparison["mapped_policies"]),
        remaining_mappings=comparison["missing_audit_mappings"],
        test_count=sum(int(s.attrib["tests"]) for s in suites),
        tests_sha256=digest(root / "tests.xml"),
        factor_reuse_component_observations=[r["mean_sum_seconds"] for r in factors],
        runtime_numeric_source_changed=False,
        production_modified=False,
    )
    for name in (
        "probe.json",
        "comparison002.json",
        "factor-reuse.json",
        "factor-reuse002.json",
        "factor-reuse003.json",
    ):
        (out / name).write_bytes((root / name).read_bytes())
    (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(9, 4))
    fig.subplots_adjust(left=0.22, right=0.97, top=0.8, bottom=0.25)
    for i, value in enumerate(seconds.values()):
        ax.barh(i, value, color=["#777777", "#3465a4"][i])
        ax.text(value, i, f"  {value:.2f} s", va="center")
    ax.set(
        yticks=[0, 1],
        yticklabels=["Original assembly", "Scatter assembly"],
        xlim=(0, seconds["reference"] * 1.28),
        xlabel="Summed likelihood compute (seconds)",
    )
    ax.invert_yaxis()
    ax.set_title(
        "DS26-0002 · 6,772 exact paired likelihood calls\n"
        "Both arms, full scientific snapshot and eight PNGs unchanged"
    )
    fig.text(
        0.5,
        0.03,
        "Component observations from a dual-execution probe.\n"
        "Not a full-pipeline timing comparison; runtime optimization remains experimental.",
        ha="center",
        fontsize=9,
    )
    fig.savefig(out / "likelihood-comparison.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    run(parser.parse_args().root)
