"""Evaluate sealed paired-receiver grid comparisons; never select inference modes."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def validate_document(document):
    original = dict(document)
    expected = original.pop("content_digest")
    payload = json.dumps(original, sort_keys=True, separators=(",", ":")).encode()
    if "sha256:" + hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError("paired inference content seal mismatch")
    if any(
        document.get(key) is not False
        for key in (
            "truth_accessed",
            "known_position_used",
            "site_conditioned_candidates_used",
        )
    ):
        raise ValueError("paired comparison must be truth-independent")
    for arm in ("independent", "paired"):
        point = document[arm]
        if not np.all(np.isfinite([point["latitude_deg"], point["longitude_deg"]])):
            raise ValueError("nonfinite position")
    return document


def evaluate(paths, reference, output):
    if output.exists():
        raise ValueError("fresh evaluation directory required")
    documents = [validate_document(json.loads(path.read_text())) for path in paths]
    if len({d["branch"] for d in documents}) != len(documents):
        raise ValueError("duplicate regional branch")
    for key in ("authority", "evidence", "runner"):
        if len({d["provenance"][key] for d in documents}) != 1:
            raise ValueError("paired comparison input/source mismatch")
    output.mkdir(parents=True)
    seal = {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
    (output / "inference-seal.json").write_text(json.dumps(seal, indent=2) + "\n")
    truth = json.loads(reference.read_text())
    latitude0, longitude0 = np.deg2rad([truth["latitude_deg"], truth["longitude_deg"]])
    rows = []
    for path, document in zip(paths, documents, strict=True):
        shutil.copyfile(path, output / path.name)
        row = {
            "branch": document["branch"],
            "arms": {},
            "applied_pair_count": len(document["pair_accounting"]),
            "excluded_pair_count": len(document["excluded_pair_accounting"]),
        }
        for name in ("independent", "paired"):
            point = document[name]
            latitude, longitude = np.deg2rad([point["latitude_deg"], point["longitude_deg"]])
            value = (
                np.sin((latitude - latitude0) / 2) ** 2
                + np.cos(latitude) * np.cos(latitude0) * np.sin((longitude - longitude0) / 2) ** 2
            )
            row["arms"][name] = dict(
                point,
                horizontal_error_km=float(2 * 6371.0088 * np.arcsin(np.sqrt(np.clip(value, 0, 1)))),
            )
        rows.append(row)
    fig, ax = plt.subplots(figsize=(10, 5))
    positions = np.arange(len(rows))
    for offset, name, label in (
        (-0.18, "independent", "Separate receiver identities"),
        (0.18, "paired", "RF-linked shared identity"),
    ):
        errors = [row["arms"][name]["horizontal_error_km"] for row in rows]
        bars = ax.bar(positions + offset, errors, 0.36, label=label)
        ax.bar_label(bars, labels=[f"{value:,.1f}" for value in errors], padding=3, fontsize=9)
    ax.set(
        xticks=positions,
        xticklabels=[r["branch"].replace("-50km", "").title() for r in rows],
        ylabel="Evaluation horizontal error (km)",
        yscale="log",
        title="Matched single-scan comparison · 50 km grid · pairing anchors excluded",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(output / "paired-position-errors.png", dpi=160)
    plt.close(fig)
    result = {
        "purpose": "evaluation_only",
        "reference": truth,
        "results": rows,
        "scope": "matched coarse-grid comparison; no local refinement or calibrated confidence",
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", type=Path, nargs="+", required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    evaluate(args.inputs, args.reference, args.output)
