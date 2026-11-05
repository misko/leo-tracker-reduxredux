"""Verify and render final-stage handoff and RF-trigger qualification."""

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
ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104/reassociation001")
OUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path):
    receipt = json.loads(path.with_suffix(".receipt.json").read_text())
    expected = receipt.get("output_sha256") or receipt["output"]["sha256"]
    assert digest(path) == expected
    for record in receipt.get("modules", {}).values():
        assert digest(record["path"]) == record["sha256"], record["path"]
    for key in ("inputs", "additional_inputs", "tool_sources"):
        for name, sha in receipt.get(key, {}).items():
            item = Path(name)
            if not item.is_absolute():
                item = Path(receipt["source"]) / item
            assert digest(item) == sha, item
    for key in ("tool", "policy", "recovery_catalogue", "preflight_packet"):
        if receipt.get(key):
            record = receipt[key]
            assert digest(record["path"]) == record["sha256"], record["path"]
    return json.loads(path.read_text()), receipt


def main():
    from compare_algo07v3_inclusion import first_difference

    paths = {
        name: ROOT / (name + ".json")
        for name in (
            "reference",
            "candidate",
            "policy-reference",
            "policy-candidate",
            "prefix-candidate",
        )
    }
    data = {name: checked(path) for name, path in paths.items()}
    assert first_difference(data["reference"][0], data["candidate"][0]) is None
    assert first_difference(data["policy-reference"][0], data["policy-candidate"][0]) is None
    candidate = data["candidate"][0]
    assert candidate["targets"] == [62116, 58002]
    assert all(len(v) == 3311 for v in candidate["owners"].values())
    earlier_path = ROOT.parent / "additional001/prefix-candidate.json"
    assert (
        digest(earlier_path) == "e0edf262da974d48ce46f49bd62aee353561ec14a455dc622245061adc1d76af"
    )
    earlier = json.loads(earlier_path.read_text())
    prefix = data["prefix-candidate"][0]
    difference = first_difference(
        earlier,
        {
            k: v
            for k, v in prefix.items()
            if k not in ("reassociation_handoff", "reassociation_trigger")
        },
    )
    assert difference is None, difference
    handoff = prefix["reassociation_handoff"]
    assert handoff["status"] == "reassociation_prepared" and not handoff["recovery_complete"]
    assert all(len(v) == 2783 for v in handoff["owners"].values())
    suite = ET.parse(ROOT / "tests.xml").getroot().find("testsuite")
    assert all(suite.attrib[key] == "0" for key in ("failures", "errors", "skipped"))
    result = dict(
        exact_handoff_likelihood_trigger=True,
        exact_policy_decisions=len(data["policy-candidate"][0]),
        selected_targets=candidate["targets"],
        ranked_families=len(candidate["ranking"]),
        retained_points_per_arm={a: len(v) for a, v in candidate["owners"].items()},
        objective_replay=candidate["replay"],
        prefix_earlier_science_exact=True,
        prefix_trigger=prefix["reassociation_trigger"],
        tests=int(suite.attrib["tests"]),
        observed_seconds={
            k: data[k][1]["seconds"] for k in ("reference", "candidate", "prefix-candidate")
        },
        full_pipeline_parity=False,
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
    )
    (OUT / "comparison.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    paths.update(previous_prefix=earlier_path, tests=ROOT / "tests.xml")
    (OUT / "artifact-bindings.json").write_text(
        json.dumps(
            {name: dict(path=str(path), sha256=digest(path)) for name, path in paths.items()},
            indent=2,
        )
        + "\n"
    )
    ranking = candidate["ranking"]
    top = ranking[:10]
    chosen = candidate["targets"]
    colors = ["#15856f" if row["norad"] in chosen else "#7e8da2" for row in top]
    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    y = np.arange(len(top))
    scores = [float.fromhex(row["rank_score"]["hex"]) for row in top]
    axes[0].barh(y, scores, color=colors)
    axes[0].set(
        yticks=y,
        yticklabels=[str(row["norad"]) for row in top],
        xlabel="Summed local RF influence across both arms (km)",
        title="Top 10 of 26 ranked families; green = selected",
    )
    axes[0].invert_yaxis()
    axes[0].axvline(0.5, color="black", linestyle="--", alpha=0.5)
    for i, row in enumerate(top):
        label = "track" if row["tracks"] == 1 else "tracks"
        axes[0].text(scores[i] + 0.012, i, f"{row['tracks']} {label}", va="center", fontsize=8)
    axes[0].set_xlim(0, max(scores) * 1.2)
    axes[1].scatter(
        [r["tracks"] for r in ranking],
        [r["points"] for r in ranking],
        c=["#15856f" if r["norad"] in chosen else "#7e8da2" for r in ranking],
        s=50,
    )
    axes[1].axvline(2, color="black", linestyle="--", alpha=0.4)
    axes[1].axhline(30, color="black", linestyle="--", alpha=0.4)
    for row in ranking:
        if row["norad"] in chosen or row["norad"] == 62997:
            axes[1].annotate(
                str(row["norad"]),
                (row["tracks"], row["points"]),
                xytext=(6, 6),
                textcoords="offset points",
            )
    axes[1].set(
        xlabel="Native graph tracks",
        ylabel="Retained native points",
        title="Trigger also requires ≥2 tracks and ≥30 points",
        xlim=(0.5, 9),
    )
    for ax in axes:
        ax.grid(alpha=0.2)
        ax.set_axisbelow(True)
    fig.suptitle(
        "DS26-0086 · exact original/v3 RF-influence trigger after additional-family adoption"
    )
    fig.text(
        0.5,
        0.02,
        "Selected for investigation, not declared wrong. "
        "All 3,311 owners per arm retained; no replacement or position change at this stage.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.94))
    fig.savefig(OUT / "reassociation-trigger.png", dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("objective_replay", "prefix_trigger")},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
