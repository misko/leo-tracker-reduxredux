"""Seal completed regional runs, then make evaluation-only comparison artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from leo.analysis.research.regional_mode_stability import regional_deletion_stability


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_run(run, single_session):
    result = json.loads((run / "result.json").read_text())
    if not result.get("complete") or result.get("position_truth_used") is not False:
        raise ValueError("finished truth-free regional result required")
    if result.get("prior_matched_norads_used", False):
        raise ValueError("site-selected identities are not blind inference inputs")
    history = json.loads((run / "history.json").read_text())
    sessions = [row["session_id"] for row in history]
    if single_session not in sessions or len(sessions) != len(set(sessions)):
        raise ValueError("single-scan membership or session uniqueness failed")
    with np.load(run / "grid.npz") as archive:
        grid = {key: archive[key] for key in archive.files}
    training, heldout = [], []
    for session in sessions:
        with np.load(run / f"{session}.npz") as archive:
            training.append(np.sum(archive["train_logbf"], axis=0))
            heldout.append(np.sum(archive["heldout_logbf"], axis=0))
    training, heldout = np.array(training), np.array(heldout)
    if training.shape != (len(sessions), len(grid["latitude_deg"])):
        raise ValueError("score map dimensions do not match grid")
    if not np.all(np.isfinite(training)) or not np.all(np.isfinite(heldout)):
        raise ValueError("nonfinite score maps")
    return result, sessions, grid, training, heldout


def evaluate(runs, single_session, truth_path, output, refinements=()):
    if output.exists():
        raise ValueError("fresh evaluation directory required")
    loaded = [load_run(run, single_session) for run in runs]
    refined = []
    for path in refinements:
        document = json.loads((path / "result.json").read_text())
        if not document.get("complete") or document.get("position_truth_used") is not False:
            raise ValueError("finished truth-free refinement required")
        expected_digest = (path / "result.sha256").read_text().strip()
        if file_digest(path / "result.json") != expected_digest:
            raise ValueError("refinement seal mismatch")
        refined.append((path, document))
    seals = {
        str(run): {
            path.name: file_digest(path)
            for path in sorted(run.iterdir())
            if path.suffix in {".json", ".npz", ".jsonl"}
        }
        for run in (*runs, *refinements)
    }
    output.mkdir(parents=True)
    (output / "inference-seal.json").write_text(json.dumps(seals, indent=2) + "\n")
    # Reference coordinate enters only after inputs have been validated and sealed.
    truth = json.loads(truth_path.read_text())
    truth_lat, truth_lon = np.deg2rad([truth["latitude_deg"], truth["longitude_deg"]])
    figures, axes = plt.subplots(2, len(runs), figsize=(6 * len(runs), 10), squeeze=False)
    records = []
    for column, (run, loaded_run) in enumerate(zip(runs, loaded, strict=True)):
        result, sessions, grid, training, heldout = loaded_run
        single_index = sessions.index(single_session)
        compact = dict(
            grid, training_by_scan=training, heldout_by_scan=heldout, session_ids=np.array(sessions)
        )
        np.savez_compressed(output / f"{run.name}-maps.npz", **compact)
        for row, (label, selected) in enumerate(
            (
                ("single", [single_index]),
                ("set", list(range(len(sessions)))),
            )
        ):
            score = np.sum(training[selected], axis=0)
            predictive = np.sum(heldout[selected], axis=0)
            best = int(np.argmax(score))
            lat, lon = np.deg2rad([grid["latitude_deg"][best], grid["longitude_deg"][best]])
            haversine = (
                np.sin((lat - truth_lat) / 2) ** 2
                + np.cos(lat) * np.cos(truth_lat) * np.sin((lon - truth_lon) / 2) ** 2
            )
            error_km = float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1))))
            stability = regional_deletion_stability(
                training[selected],
                grid["latitude_deg"],
                grid["longitude_deg"],
                [sessions[index] for index in selected],
            )
            records.append(
                {
                    "run": run.name,
                    "cohort": label,
                    "sessions": [sessions[i] for i in selected],
                    "latitude_deg": float(grid["latitude_deg"][best]),
                    "longitude_deg": float(grid["longitude_deg"][best]),
                    "horizontal_error_km": error_km,
                    "training_score": float(score[best]),
                    "heldout_score_at_training_best": float(predictive[best]),
                    "region": result["region"],
                    "spacing_km": result["spacing_km"],
                    "full_region_grid": result["full_region_grid"],
                    "stability": stability,
                }
            )
            ax = axes[row, column]
            points = ax.scatter(
                grid["longitude_deg"],
                grid["latitude_deg"],
                c=np.maximum(score - score[best], -100),
                s=5,
                vmin=-100,
                vmax=0,
            )
            ax.scatter(
                grid["longitude_deg"][best],
                grid["latitude_deg"][best],
                marker="x",
                color="red",
                s=90,
                label="Training-selected grid cell",
            )
            ax.scatter(
                truth["longitude_deg"],
                truth["latitude_deg"],
                marker="+",
                color="black",
                s=100,
                label="Evaluation reference",
            )
            ax.set(
                title=f"{run.name} / {label}\nGrid-cell error {error_km:,.1f} km",
                xlabel="Longitude (degrees)",
                ylabel="Latitude (degrees)",
            )
            figures.colorbar(points, ax=ax, label="Training score relative to maximum (clipped)")
            if row == column == 0:
                ax.legend(fontsize=8)
    figures.suptitle("Independent regional searches · coarse grid results, before local refinement")
    figures.tight_layout()
    figures.savefig(output / "regional-training-maps.png", dpi=160)
    plt.close(figures)
    refinement_records = []
    for path, document in refined:
        lat, lon = np.deg2rad([document["latitude_deg"], document["longitude_deg"]])
        haversine = (
            np.sin((lat - truth_lat) / 2) ** 2
            + np.cos(lat) * np.cos(truth_lat) * np.sin((lon - truth_lon) / 2) ** 2
        )
        error = float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(haversine, 0, 1))))
        row = {
            key: document[key]
            for key in (
                "latitude_deg",
                "longitude_deg",
                "training_score",
                "heldout_score",
                "track_count",
                "observation_count",
                "sessions",
                "selected",
                "fits",
                "identity_refreshed_at_every_position",
                "nominal_exact_orbits",
                "geometry_pair_factor_used",
                "elapsed_s",
                "peak_rss_kib",
            )
        }
        row.update(run=path.name, horizontal_error_km=error)
        refinement_records.append(row)
        (output / f"{path.name}.json").write_text(json.dumps(document, indent=2) + "\n")
    if refinement_records:
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.bar(
            [row["run"] for row in refinement_records],
            [row["horizontal_error_km"] for row in refinement_records],
        )
        ax.axhline(1, color="black", linestyle="--", label="1 km reference")
        ax.set(
            yscale="log",
            ylabel="Evaluation horizontal error (km)",
            title="Full-observation local refinement · identities refreshed at every position",
        )
        ax.tick_params(axis="x", rotation=30)
        ax.legend()
        fig.tight_layout()
        fig.savefig(output / "refined-position-errors.png", dpi=160)
        plt.close(fig)
    receipt = {
        "purpose": "evaluation_only",
        "single_session": single_session,
        "truth": truth,
        "results": records,
        "refinements": refinement_records,
        "calibrated_uncertainty": False,
    }
    (output / "summary.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", nargs="+", type=Path, required=True)
    parser.add_argument("--single-session", required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--refinements", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    evaluate(args.runs, args.single_session, args.truth, args.output, args.refinements)
