"""Verify owned final reassociation, complete fits and connected numerical path."""

import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
ROOT = Path("/srv/bulk/leo/research/algo07v3-20261104")
OUT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def checked(path):
    receipt = json.loads(path.with_suffix(".receipt.json").read_text())
    assert digest(path) == (receipt.get("output_sha256") or receipt["output"]["sha256"])
    for record in receipt.get("modules", {}).values():
        assert digest(record["path"]) == record["sha256"], record["path"]
    for key in ("inputs", "additional_inputs", "tool_sources"):
        for name, sha in receipt.get(key, {}).items():
            source = Path(name)
            if not source.is_absolute():
                source = Path(receipt.get("source", REPO)) / source
            assert digest(source) == sha, source
    for key in ("tool", "recovery_catalogue", "reassociation_history_bank"):
        if receipt.get(key):
            record = receipt[key]
            assert digest(record["path"]) == record["sha256"], record["path"]
    return json.loads(path.read_text()), receipt


def number(value):
    return float.fromhex(value["hex"])


def main():
    from compare_algo07v3_inclusion import first_difference

    paths = {
        name: ROOT / "reassociation-final004" / (name + ".json")
        for name in ("reference", "candidate", "history-reference", "history-candidate")
    }
    paths["prefix-candidate"] = ROOT / "reassociation-final002/prefix-candidate.json"
    data = {name: checked(path) for name, path in paths.items()}
    for reference, candidate in [
        ("reference", "candidate"),
        ("history-reference", "history-candidate"),
    ]:
        difference = first_difference(data[reference][0], data[candidate][0])
        assert difference is None, difference
    history = data["history-candidate"][0]["history"]
    assert history["before"] == history["original_after"]
    for category in ("control_fits", "candidate_fits"):
        rows = history[category]
        assert len(rows) == 4 and all(r["status"] == "complete" and r["qualified"] for r in rows)
    final = data["candidate"][0]["complete_final"]
    assert final["selected"] == "62025_to_68047" and final["execution_status"] == "complete"
    record = final["records"][0]
    arms = {}
    for arm in ("c0", "fitted_c"):
        fit = record["pair"][arm]
        assert not fit["lost_ids"] and not fit["added_ids"] and not fit["unexpected_reassigned_ids"]
        assert final["final"][arm]["associated"] == len(fit["proposed_owners"]) == 2770
        arms[arm] = dict(
            original_objective=number(final["baseline"][arm]["objective"]),
            matched_history_endpoint=number(record["matched_published_objectives"][arm]),
            best_control=number(record["control"][arm]["objective"]),
            best_replacement=number(fit["objective"]),
            paired_gain=number(record["gains"][arm]),
            retained_owners=len(fit["proposed_owners"]),
            reassigned=len(fit["reassigned_ids"]),
            rms_hz=number(fit["rms_hz"]),
        )
    previous_path = ROOT / "reassociation-screen002/prefix-candidate.json"
    assert (
        digest(previous_path) == "c8f496518e034c78aea84ee0b266455eabcf5756486f645201b27e14c3a6ddd9"
    )
    previous = json.loads(previous_path.read_text())
    prefix = data["prefix-candidate"][0]
    difference = first_difference(
        previous, {k: v for k, v in prefix.items() if k != "reassociation_complete"}
    )
    assert difference is None, difference
    completed = prefix["reassociation_complete"]
    assert completed["status"] == "reassociation_evaluated" and completed["recovery_complete"]
    assert completed["recovery"]["selected"] is None
    assert completed["recovery"]["final"] == completed["recovery"]["baseline"]
    assert all(v["associated"] == 2783 for v in completed["recovery"]["final"].values())
    suite = ET.parse(ROOT / "reassociation-final003/tests.xml").getroot().find("testsuite")
    assert all(suite.attrib[k] == "0" for k in ("failures", "errors", "skipped"))
    summary = dict(
        exact_final_controller=True,
        exact_all_eight_fits=True,
        history_completion=final["history"],
        replacement_history=record["history"],
        selected=final["selected"],
        arms=arms,
        shortlist_penalty=number(record["hypothesis"]["penalty"]),
        prefix_earlier_science_exact=True,
        prefix_recovery_complete=True,
        prefix_selected=None,
        prefix_owners_per_arm=2783,
        tests=int(suite.attrib["tests"]),
        observed_seconds={name: receipt["seconds"] for name, (_, receipt) in data.items()},
        publication_qualified=False,
        full_pipeline_parity=False,
        complete_path_matched_scans=0,
        end_to_end_speedup=None,
    )
    (OUT / "comparison.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    paths.update(previous_prefix=previous_path, tests=ROOT / "reassociation-final003/tests.xml")
    (OUT / "artifact-bindings.json").write_text(
        json.dumps(
            {name: dict(path=str(path), sha256=digest(path)) for name, path in paths.items()},
            indent=2,
        )
        + "\n"
    )
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), sharey=True)
    for ax, (arm, row) in zip(axes, arms.items(), strict=True):
        keys = [
            "original_objective",
            "matched_history_endpoint",
            "best_control",
            "best_replacement",
        ]
        values = [row[key] - row["original_objective"] for key in keys]
        ax.bar(range(4), values, color=["#888888", "#8db8d1", "#348abd", "#38a169"])
        ax.set_xticks(
            range(4),
            [
                "Original\nselected",
                "History at\nsame point",
                "Matched\ncontrol",
                "Satellite\nreplacement",
            ],
        )
        ax.axhline(0, color="black", linewidth=0.7)
        for k, value in enumerate(values):
            ax.annotate(
                f"{value:.2f}",
                (k, value),
                xytext=(0, -14 if value < 0 else 5),
                textcoords="offset points",
                ha="center",
            )
        ax.set_title(f"{arm} · accepted paired gain {row['paired_gain']:.3f}")
        ax.grid(axis="y", alpha=0.2)
        ax.set_ylim(min(values) - 25, 12)
    axes[0].set_ylabel(
        "RF objective change from original selected endpoint\n(lower is better; not position error)"
    )
    fig.suptitle("DS26-0066 · 62025 → 68047 · exact final-stage equivalence")
    fig.text(
        0.5,
        0.015,
        "2,770 retained points per arm · 170 reassigned · no points added or lost\n"
        "History improvement alone cannot be published; "
        "replacement must beat matched controls plus penalty.",
        ha="center",
        fontsize=9,
    )
    fig.tight_layout(rect=(0, 0.075, 1, 0.93))
    fig.savefig(OUT / "matched-reassociation.png", dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
