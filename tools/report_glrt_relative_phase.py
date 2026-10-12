"""Retain measured cohort surfaces and separate frequency fit from position error."""

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

from leo.analysis.wrapped_glrt_likelihood import WrappedConfig
from tools.evaluate_sparse_glrt import local_output, write_json
from tools.evaluate_wrapped_fast_scan import load_bundle, load_phase_bank, phase_provider
from tools.report_wrapped_glrt_cohort import metrics


def surface_summary(result, rows, arm):
    if not rows or (rows[0]["east_m"], rows[0]["north_m"]) != (0.0, 0.0):
        raise ValueError("reference must be the first measured surface point")
    scores = np.array([r["arms"][arm]["score"] for r in rows])
    if not np.isfinite(scores).all():
        raise ValueError("finite measured scores required")
    best = rows[int(scores.argmax())]
    gap = float(scores.max() - scores[0])
    return dict(
        completed=result["completed"],
        evaluations=len(rows),
        random_points=sum(r["kind"] == "random" for r in rows),
        reference_score=float(scores[0]),
        best_score=float(scores.max()),
        best_east_m=best["east_m"],
        best_north_m=best["north_m"],
        best_distance_m=best["distance_m"],
        reference_score_gap=gap,
        conditional_gate_met=bool(
            result["completed"] and best["distance_m"] <= 1000 and gap <= 1.0
        ),
        scope=result["candidate_scope"],
        full_catalogue_audit_required=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data-root", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--surface-directory", default="local-relative-warm-v1")
    p.add_argument("--audit-directory", default="full-catalogue-audit-warm-v1")
    args = p.parse_args()
    local_output(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    panel = json.loads((args.data_root / "panel.json").read_text())
    items = []
    for entry in panel["rows"]:
        root = args.data_root / entry["session_id"]
        path = root / args.surface_directory
        if not (path / "result.json").exists():
            items.append(dict(entry, status="not completed; retained in cohort denominator"))
            continue
        result = json.loads((path / "result.json").read_text())
        rows = [json.loads(line) for line in (path / "evaluations.jsonl").read_text().splitlines()]
        data, bank, meta, receipt = load_bundle(root / "bundle")
        if (
            result["input_digest"] != meta["input_sha256"]
            or result["orbit_digest"] != meta["orbit_bank_sha256"]
        ):
            raise ValueError("surface provenance does not match the recording")
        phases, _ = load_phase_bank(root / "bundle", bank)
        provider = phase_provider(
            phases,
            bank,
            data,
            meta["site"],
            (0.0, 0.0),
            inertial_phase=result.get("phase_model") == "fixed-reception-frame-orbital-phase",
        )
        lookup = {int(n): i for i, n in enumerate(bank["norad"])}
        pool = [lookup[int(n)] for n in result["candidate_norad"]]
        arms = {}
        for arm in ("zero-c", "fitted-c"):
            fit = rows[0]["arms"][arm]
            active = np.asarray(fit["active"])
            full_active = np.array(pool)[active]
            delta = np.array(fit["satellite_phase_s"])[active]
            pred, opp, _, _ = provider.predict(fit["phase_s"] + delta, full_active)
            local_fit = dict(fit, active=list(range(len(active))))
            arms[arm] = dict(
                surface_summary(result, rows, arm),
                reference_frequency=metrics(
                    data, pred, opp, bank["rf_hz"], local_fit, WrappedConfig(**result["config"])
                ),
            )
        destination = args.output / entry["session_id"]
        destination.mkdir(exist_ok=True)
        for filename in ("result.json", "evaluations.jsonl", "protocol.json"):
            shutil.copyfile(path / filename, destination / filename)
        for folder in (
            "relative-shape-initial",
            "relative-shape-initial-v2",
            "reference-relative-shape-v1",
            "full-catalogue-audit-v1",
        ):
            source = root / folder
            if source.exists():
                shutil.copytree(source, destination / folder, dirs_exist_ok=True)
        for filename in ("warm-local-pool.json", "warm-common-initial.json"):
            shutil.copyfile(root / filename, destination / filename)
        for earlier in (
            "local-relative-final-v1",
            "local-relative-pool-v1",
            "local-relative-lbfgs-v1",
            args.audit_directory,
            "full-catalogue-audit-extra-v1",
        ):
            if (root / earlier / "result.json").exists():
                shutil.copytree(root / earlier, destination / earlier, dirs_exist_ok=True)
        items.append(
            dict(
                entry,
                arms=arms,
                evidence_receipt=receipt,
                candidate_count=len(pool),
                catalogue_count=len(bank["norad"]),
            )
        )
    write_json(
        args.output / "cohort-summary.json",
        dict(
            rows=items,
            validation_passes={
                a: sum(
                    x.get("arms", {}).get(a, {}).get("conditional_gate_met", False)
                    for x in items
                    if x["split"] == "validation"
                )
                for a in ("zero-c", "fitted-c")
            },
            validation_denominator=4,
            interpretation="conditional local frequency surfaces; full-catalogue audit required",
        ),
    )
    # Preserve every JSON value while avoiding hundreds of thousands of pretty
    # printed zero entries in full-catalogue phase vectors. Pool byte digests
    # are part of the protocol, so those files retain their original bytes.
    for receipt_path in args.output.rglob("*.json"):
        if "pool" not in receipt_path.name:
            payload = json.loads(receipt_path.read_text())
            receipt_path.write_text(
                json.dumps(payload, separators=(",", ":"), allow_nan=False) + "\n"
            )

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    measured = [x for x in items if "arms" in x]
    fig, axes = plt.subplots(
        len(measured), 2, figsize=(11, 4 * len(measured)), squeeze=False, constrained_layout=True
    )
    for i, entry in enumerate(measured):
        rows = [
            json.loads(line)
            for line in (args.output / entry["session_id"] / "evaluations.jsonl")
            .read_text()
            .splitlines()
        ]
        for j, arm in enumerate(("zero-c", "fitted-c")):
            ax = axes[i, j]
            summary = entry["arms"][arm]
            loss = [summary["best_score"] - r["arms"][arm]["score"] for r in rows]
            scatter = ax.scatter(
                [r["east_m"] / 1000 for r in rows],
                [r["north_m"] / 1000 for r in rows],
                c=loss,
                cmap="viridis_r",
                vmin=0,
                vmax=100,
                s=35,
            )
            ax.scatter(0, 0, marker="*", s=180, c="red", label="configured reference")
            ax.scatter(
                summary["best_east_m"] / 1000,
                summary["best_north_m"] / 1000,
                marker="x",
                s=90,
                c="black",
                label="best evaluated point",
            )
            ax.set(
                xlabel="East (km)",
                ylabel="North (km)",
                xlim=(-5.2, 5.2),
                ylim=(-5.2, 5.2),
                aspect="equal",
                title=f"{entry['session_id'][5:13]} {entry['split']} / {arm}\n"
                f"best {summary['best_distance_m'] / 1000:.2f} km; "
                f"reference gap {summary['reference_score_gap']:.2f}",
            )
            ax.legend(fontsize=7)
            fig.colorbar(scatter, ax=ax, label="loss above best (clipped at 100)")
    fig.suptitle("Measured local GLRT surfaces; exact sampled points, no interpolated minimum")
    fig.savefig(args.output / "local-surfaces.png", dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    labels = [x["session_id"][5:13] + " " + x["split"][:3] for x in measured]
    for j, arm in enumerate(("zero-c", "fitted-c")):
        offset = (j - 0.5) * 0.35
        axes[0].bar(
            np.arange(len(measured)) + offset,
            [
                100 * x["arms"][arm]["reference_frequency"]["strong_signal_fraction"]
                for x in measured
            ],
            width=0.35,
            label=arm,
        )
        axes[1].bar(
            np.arange(len(measured)) + offset,
            [x["arms"][arm]["best_distance_m"] / 1000 for x in measured],
            width=0.35,
            label=arm,
        )
    for ax in axes:
        ax.set_xticks(np.arange(len(measured)), labels, rotation=35, ha="right")
        ax.legend()
    axes[0].set(
        ylabel="Strong signal responsibility (%)",
        ylim=(0, 100),
        title="Frequency evidence at reference",
    )
    axes[1].set(
        ylabel="Distance from configured reference (km)",
        title="Position error of best evaluated point",
    )
    axes[1].axhline(1.0, color="red", linestyle="--", linewidth=1)
    fig.savefig(args.output / "fit-versus-position.png", dpi=160)
    plt.close(fig)
    print(
        json.dumps(
            dict(
                measured_scans=len(measured),
                validation_scans=sum(x["split"] == "validation" for x in measured),
            )
        )
    )


if __name__ == "__main__":
    main()
