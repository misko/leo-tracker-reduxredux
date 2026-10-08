"""Reconcile full dataset membership and prior research exposure without new outcomes."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent
AUTHORITY = Path("/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_08_ds18_post_ds17")


def main():
    if (HERE / "membership.json").exists():
        raise FileExistsError("Preserve first membership/exposure reconciliation")
    sources = {}

    def read(path):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return json.loads(path.read_text())

    manifests = {
        "DS16": read(REPORTS / "2026_10_08_ds16_last16h/manifest.json"),
        "DS17": read(REPORTS / "2026_10_08_position_error_iter01/ds17-manifest.json"),
        "DS18": read(AUTHORITY / "local/manifest.json"),
    }
    verification = read(AUTHORITY / "verification.json")
    assert sources[str(AUTHORITY / "local/manifest.json")] == verification["manifest_sha256"]
    prior16 = read(REPORTS / "2026_10_08_hard60_bounded_recovery/frozen-inputs.json")
    prior17 = read(REPORTS / "2026_10_08_position_error_iter01/protocol.json")
    old16 = {
        r["session_id"]: dict(label=label, historical_group=r["group"])
        for label, r in prior16.items()
    }
    old17 = {r["session_id"]: r for r in prior17["membership"]}
    old18 = {r["session_id"]: r for r in verification["exposure"]}
    # Preserve existing labels and split provenance; all matched outcomes are consumed.
    split18 = read(REPORTS / "2026_10_08_position_error_iter18/newer-random-split.json")
    split26 = read(REPORTS / "2026_10_08_position_error_iter26/newer-random-split.json")
    groups = {
        r["session_id"]: dict(group=r["group"], protocol=path)
        for split, path in (
            (split18, "iteration18 random split"),
            (split26, "iteration26 random split"),
        )
        for r in split["captures"]
    }
    old27 = {
        r["label"]: r
        for r in read(REPORTS / "2026_10_08_position_error_iter27/summary.json")["cases"]
    }
    old29 = {
        r["member"]["label"]: r
        for r in read(REPORTS / "2026_10_08_position_error_iter29/summary.json")["cases"]
    }
    rows, seen = [], set()
    for dataset, manifest in manifests.items():
        assert len(manifest["captures"]) == {"DS16": 63, "DS17": 51, "DS18": 34}[dataset]
        for i, capture in enumerate(manifest["captures"], 1):
            session = capture["session_id"]
            assert session not in seen
            seen.add(session)
            row = dict(
                dataset=dataset,
                inventory_label=capture.get("dataset_label", f"DS16-M{i:03d}"),
                session_id=session,
                capture_start_utc_ns=capture["capture_start_utc_ns"],
                source_kind=capture.get("source_kind", "published"),
                recording_manifest_sha256=capture.get("recording_manifest_sha256"),
                uncompressed_sha256=capture.get("uncompressed_sha256"),
                metadata_snapshot_sha256=capture.get("metadata_snapshot_sha256"),
                legacy_labels=[],
                historical_groups=[],
                research_errors=None,
                exposure="not_matched_in_reviewed_registry_not_unseen_claim",
            )
            if dataset == "DS16" and session in old16:
                row["legacy_labels"] = [old16[session]["label"]]
                row["historical_groups"] = [
                    dict(
                        group=old16[session]["historical_group"],
                        protocol="bounded recovery random split",
                    )
                ]
            elif dataset == "DS17":
                row["legacy_labels"] = [old17[session]["label"]]
                row["historical_groups"] = [
                    dict(group=old17[session]["group"], protocol="iteration01 random split")
                ]
            elif dataset == "DS18":
                row["legacy_labels"] = sorted(
                    {r["label"] for r in old18[session]["prior_evidence"]}
                )
                row["prior_evidence"] = old18[session]["prior_evidence"]
                if session in groups:
                    row["historical_groups"] = [groups[session]]
                elif row["legacy_labels"]:
                    row["historical_groups"] = [
                        dict(group="chronological challenge", protocol="preserved NEW/LATER cohort")
                    ]
            if row["legacy_labels"]:
                row["exposure"] = "previously_evaluated_consumed"
                assert len(row["legacy_labels"]) == 1
                label = row["legacy_labels"][0]
                if label in old27:
                    row["research_errors"] = {
                        arm: values["sigma-0.25"] for arm, values in old27[label]["arms"].items()
                    }
                else:
                    row["research_errors"] = {
                        arm: values["variants"]["slope-0.25"]
                        for arm, values in old29[label]["arms"].items()
                    }
            row["evaluation_status"] = (
                "prior_research_available" if row["research_errors"] else "pending"
            )
            rows.append(row)
    assert len(rows) == 148
    assert sum(r["research_errors"] is not None for r in rows) == 123
    metrics = {}
    for dataset in manifests:
        members = [r for r in rows if r["dataset"] == dataset]
        complete = [r for r in members if r["research_errors"]]
        metrics[dataset] = dict(
            members=len(members),
            prior_research=len(complete),
            pending=len(members) - len(complete),
            arms={},
        )
        for arm in ("fitted-c", "zero-c"):
            values = np.array([r["research_errors"][arm]["error_km"] for r in complete])
            metrics[dataset]["arms"][arm] = dict(
                mean_km=float(values.mean()),
                median_km=float(np.median(values)),
                p95_km=float(np.percentile(values, 95)),
                worst_km=float(values.max()),
            )
    fig, ax = plt.subplots(figsize=(8, 4), constrained_layout=True)
    names = list(metrics)
    available = [metrics[n]["prior_research"] for n in names]
    ax.bar(names, available, label="Prior research results (consumed)")
    ax.bar(
        names,
        [metrics[n]["pending"] for n in names],
        bottom=available,
        label="Pending research evaluation",
    )
    ax.set(ylabel="Recordings", title="Full manifest membership; no readiness filtering")
    ax.legend()
    fig.savefig(HERE / "coverage.png", dpi=150)
    (HERE / "membership.json").write_text(
        json.dumps(dict(members=rows, sources=sources), indent=2) + "\n"
    )
    (HERE / "coverage.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
