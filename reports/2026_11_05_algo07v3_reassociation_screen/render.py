"""Verify causal nomination and receiver-shared admission before rendering."""

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
ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104/reassociation-screen002")
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
    for key in ("tool", "recovery_catalogue", "preflight_packet"):
        if receipt.get(key):
            record = receipt[key]
            assert digest(record["path"]) == record["sha256"], record["path"]
    return json.loads(path.read_text()), receipt


def number(value):
    return float.fromhex(value["hex"])


def main():
    from compare_algo07v3_inclusion import first_difference

    paths = {
        name: ROOT / (name + ".json") for name in ("reference", "candidate", "prefix-candidate")
    }
    data = {name: checked(path) for name, path in paths.items()}
    assert first_difference(data["reference"][0], data["candidate"][0]) is None
    science = data["candidate"][0]["screening"]
    assert science["eligible"]
    assert [row["name"] for row in science["admitted"]] == ["62025_to_68047"]
    guard = science["guards"]["62025_to_68047"]
    assert guard["passed"] and guard["unique_folds"] == 10
    earlier_path = ROOT.parent / "reassociation001/prefix-candidate.json"
    assert (
        digest(earlier_path) == "954d7365df016e25f7bab3c80813815db96ea06f6dade16f6c1b55c43c5cc890"
    )
    earlier = json.loads(earlier_path.read_text())
    prefix = data["prefix-candidate"][0]
    difference = first_difference(
        earlier, {k: v for k, v in prefix.items() if k != "reassociation_screen"}
    )
    assert difference is None, difference
    admission = prefix["reassociation_screen"]
    assert admission["status"] == "reassociation_candidates_screened"
    assert not admission["recovery_complete"]
    suite = ET.parse(ROOT / "tests.xml").getroot().find("testsuite")
    assert all(suite.attrib[key] == "0" for key in ("failures", "errors", "skipped"))
    result = dict(
        exact_catalogue_screen_guard_controller=True,
        catalogue_candidates=science["catalogue_audit"]["candidate_count"],
        catalogue_classifications=science["catalogue_audit"]["classification_counts"],
        nominees=science["screen"]["nominees"],
        native_points=science["screen"]["points"],
        graph_tracks=len(science["screen"]["tracks"]),
        admitted="62025_to_68047",
        unique_folds=guard["unique_folds"],
        minimum_competitor_margin=number(guard["minimum_margin"]),
        newly_associated_points=0,
        position_changed=False,
        prefix_earlier_science_exact=True,
        prefix_status=admission["admission"]["status"],
        prefix_admitted=[row["hypothesis"]["name"] for row in admission["admission"]["admitted"]],
        prefix_screen_status={
            n: row["status"] for n, row in admission["admission"]["screens"].items()
        },
        tests=int(suite.attrib["tests"]),
        observed_seconds={k: data[k][1]["seconds"] for k in data},
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
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    inherited = next(p for p in science["screen"]["proposals"] if p["name"] == result["admitted"])
    for arm in ("c0", "fitted_c"):
        gains = [number(v) for v in inherited["predictive"][arm]["gains"]]
        axes[0].plot(np.arange(1, len(gains) + 1), gains, "o-", label=arm)
        competitor = next(
            row for row in guard["competitors"] if row["arm"] == arm and row["norad"] == 62025
        )
        margins = [number(v) for v in competitor["margins"]]
        axes[1].plot(np.arange(1, len(margins) + 1), margins, "o-", label=arm)
    axes[0].set(
        title="Inherited track-offset predictive check",
        xlabel="Synchronized held partition",
        ylabel="Held-out score gain over incumbent",
        xticks=np.arange(1, 6),
    )
    axes[1].set(
        title="Receiver-shared competition: all distinct folds",
        xlabel="Unique held partition",
        ylabel="Competitor score − proposed score",
        xticks=np.arange(1, 11),
    )
    for ax in axes:
        ax.axhline(0, color="black", linestyle="--", alpha=0.5)
        ax.grid(alpha=0.2)
        ax.legend()
    fig.suptitle("DS26-0066 · 62025 → 68047 · original and owned v3 outputs match exactly")
    fig.text(
        0.5,
        0.015,
        "140 native points across 5 tracks · minimum shared-guard margin 47.257 · "
        "admission to replacement fitting, not final acceptance",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.05, 1, 0.93))
    fig.savefig(OUT / "predictive-admission.png", dpi=160)
    plt.close(fig)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
