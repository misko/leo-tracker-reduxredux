"""Render only verified exact-fit and connected-prefix evidence."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104")
OUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path):
    data = json.loads(path.read_text())
    receipt = json.loads(path.with_suffix(".receipt.json").read_text())
    expected = receipt.get("output_sha256") or receipt["output"]["sha256"]
    assert digest(path) == expected
    for record in receipt["modules"].values():
        assert digest(record["path"]) == record["sha256"], record["path"]
    for key in ("inputs", "additional_inputs", "tool_sources"):
        for name, sha in receipt.get(key, {}).items():
            item = Path(name)
            if not item.is_absolute():
                item = Path(receipt["source"]) / item
            assert digest(item) == sha, item
    for key in ("tool", "recovery_catalogue", "preflight_packet"):
        if receipt.get(key):
            record = receipt[key]
            assert digest(record["path"]) == record["sha256"], record["path"]
    return data, receipt


def main():
    from compare_algo07v3_additional_recovery import compare
    from compare_algo07v3_inclusion import first_difference

    paths = {name: ROOT / "additional002" / (name + ".json") for name in ("reference", "candidate")}
    data = {name: checked(path) for name, path in paths.items()}
    result = compare(data["reference"][0], data["candidate"][0])
    prefix_path = ROOT / "additional001/prefix-candidate.json"
    prefix, prefix_receipt = checked(prefix_path)
    earlier_path = ROOT / "checkpoint002/prefix-candidate.json"
    assert (
        digest(earlier_path) == "876bc26318fb28dc6cf6a326ead4b10c0471f1024d885a1faacdd1ee98ce0cd3"
    )
    earlier = json.loads(earlier_path.read_text())
    difference = first_difference(
        earlier, {k: v for k, v in prefix.items() if k != "additional_position"}
    )
    assert difference is None, difference
    additional = prefix["additional_position"]
    assert additional["status"] == "additional_position_evaluated"
    assert not additional["recovery_complete"]
    tests_path = ROOT / "additional001/tests-fixed.xml"
    suite = ET.parse(tests_path).getroot().find("testsuite")
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    result.update(
        prefix_earlier_science_exact=True,
        prefix_additional_decision=additional["recovery"]["decisions"]["72h_30s"],
        prefix_seconds=prefix_receipt["seconds"],
        observed_component_seconds={k: v[1]["seconds"] for k, v in data.items()},
        tests=int(suite.attrib["tests"]),
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
    )
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    paths.update(prefix=prefix_path, previous_prefix=earlier_path, tests=tests_path)
    bindings = {k: dict(path=str(p), sha256=digest(p)) for k, p in paths.items()}
    (OUT / "artifact-bindings.json").write_text(json.dumps(bindings, indent=2) + "\n")

    candidate = data["candidate"][0]
    trial = candidate["trials"][candidate["decisions"]["72h_30s"]["trial"]]
    arms = ("c0", "fitted_c")
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.3))
    x = np.arange(2)
    before = [trial["arms"][a]["baseline_associated"] for a in arms]
    after = [n + result["newly_associated_points_per_arm"] for n in before]
    axes[0].bar(x - 0.18, before, 0.36, label="Retained", color="#687b91")
    bars = axes[0].bar(x + 0.18, after, 0.36, label="Qualified addition", color="#15856f")
    axes[0].bar_label(bars, padding=3)
    axes[0].set(
        xticks=x,
        xticklabels=arms,
        ylabel="Associated native GLRT points",
        title="26 points recovered in both arms",
        ylim=(0, max(after) * 1.15),
    )
    axes[0].legend(fontsize=8)
    for arm in arms:
        details = trial["arms"][arm]["family_details"]
        rms = [float.fromhex(f["diagnostics"][0]["profile_RMS_hz"]["hex"]) for f in details]
        axes[1].plot(["Incumbent family", "New family"], rms, "o-", label=arm)
    axes[1].set(ylabel="Profile residual RMS (Hz)", title="Joint shared-receiver fit")
    axes[1].legend(fontsize=8)
    for i, tag in enumerate(("control", "candidate")):
        counts = [result["arms"][a][tag + "_evaluations"] for a in arms]
        bars = axes[2].bar(x + (i - 0.5) * 0.36, counts, 0.36, label=tag)
        axes[2].bar_label(bars, padding=3)
    axes[2].set(
        xticks=x,
        xticklabels=arms,
        ylabel="Objective evaluations",
        title="Original and v3 histories match exactly",
        ylim=(0, 70),
    )
    axes[2].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle("DS26-0086 · standalone conditional satellite addition · NORAD 67652")
    fig.text(
        0.5,
        0.015,
        "Both calibration arms and all acceptance gates match. "
        "Component qualification; complete pipeline and speedup remain unqualified.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(OUT / "additional-position.png", dpi=160)
    plt.close(fig)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
