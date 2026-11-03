"""Audit recorded carrier references against nominal eight-tone pilot centers."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def center_residuals(rf, channel):
    rf = np.asarray(rf, dtype=float)
    channel = np.asarray(channel, dtype=float)
    if (
        rf.ndim != 1 or not len(rf) or channel.shape != rf.shape
        or np.any(~np.isfinite(rf)) or np.any(~np.isfinite(channel))
        or np.any(channel != np.floor(channel))
        or np.any((channel < 1) | (channel > 8))
    ):
        raise ValueError("finite aligned RF values and integer channels 1..8 required")
    lower = 10_709_687_500.0 + (channel - 1) * 250_000_000.0
    upper = 10_940_312_500.0 + (channel - 1) * 250_000_000.0
    nominal = np.where(np.abs(rf - lower) <= np.abs(rf - upper), lower, upper)
    return rf - nominal


def run():
    selection_path = ROOT / "selection.json"
    tuning_path = ROOT.parents[1] / "src/leo/acquisition/starlink_tuning.py"
    source_hashes = {str(path): digest(path) for path in (
        Path(__file__).resolve(), selection_path, tuning_path,
    )}
    selection = json.loads(selection_path.read_text())
    rows = []
    for dataset in ("DS10", "DS11"):
        singles = [unit for unit in selection["datasets"][dataset]["units"] if unit["size"] == 1]
        if len(singles) != 16:
            raise ValueError("expected 16 frozen singles per dataset")
        for unit in singles:
            fit_path = ROOT / "runs/finite-set-tau-profile-v1" / unit["unit_id"] / "fit.json"
            source_hashes[str(fit_path)] = digest(fit_path)
            fit = json.loads(fit_path.read_text())
            if fit["unit"] != unit or fit["dataset"] != dataset:
                raise ValueError("fit unit identity differs from selection")
            archive = ROOT / "scans" / unit["session_ids"][0] / "bundle.npz"
            source_hashes[str(archive)] = digest(archive)
            if fit["source_hashes"].get(str(archive)) != source_hashes[str(archive)]:
                raise ValueError("RF archive is not bound to the selected fit")
            with np.load(archive, allow_pickle=False) as bundle:
                residual = center_residuals(bundle["rf"], bundle["channel"])
                centers = np.unique(bundle["rf"]).tolist()
            maximum = float(np.max(np.abs(residual)))
            rows.append({
                "unit_id": unit["unit_id"], "observation_count": len(residual),
                "recorded_rf_centers_hz": centers,
                "maximum_nominal_center_difference_hz": maximum,
                "maximum_doppler_difference_hz_at_10_km_s": maximum * 10 / 299792.458,
            })
    if any(digest(path) != expected for path, expected in source_hashes.items()):
        raise RuntimeError("audit inputs changed")
    return {
        "schema": "rf-center-cohort-audit/v1", "source_hashes": source_hashes,
        "units": rows, "reference_accessed": False, "fit_performed": False,
        "scope": (
            "Recorded RF compared with the nearest lower/upper eight-tone center of its "
            "declared channel. Does not independently measure physical LNB/transmitter LO, "
            "validate edge identity, or exclude unequal pilot-tone weighting. The 10 km/s "
            "Doppler calculation is an explicit conservative sensitivity assumption."
        ),
    }


if __name__ == "__main__":
    receipt = run()
    output = ROOT / "rf-center-cohort-audit-v1.json"
    with output.open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({"output": str(output), "maximum_difference_hz": max(
        row["maximum_nominal_center_difference_hz"] for row in receipt["units"]
    )}))
