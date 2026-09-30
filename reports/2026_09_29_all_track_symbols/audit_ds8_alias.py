"""Verify DS8 recovery aliases and isolate genuinely additional carrier coverage."""

import hashlib
import json
from pathlib import Path

import numpy as np
from decode_tracks import ROOT
from local_header_recovery import score, select_positions

BASE = Path(__file__).parent


def main():
    inventory_path = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    receipt_path = BASE / "local/paired-ds8/summary.json"
    receipt = json.loads(receipt_path.read_text())
    inventory = json.loads(inventory_path.read_text())
    aliases = []
    for entry in inventory:
        if entry["session"] != receipt["source_capture"]["session"] or entry["visit"] != 1498:
            continue
        old = {s["row"]["probe"]["receiver_id"]: s["row"] for s in entry["streams"]}
        if all(
            old[rx]["excerpt_sha256"] == receipt["sources"][rx]["excerpt_sha256"]
            and old[rx]["candidate"] == receipt["sources"][rx]["candidate"]
            for rx in (0, 1)
        ):
            aliases.append(entry["signal"])
    assert aliases == ["S13"]
    old_path = ROOT / "reports/2026_09_28_sequence_semantics/local/S13-soft.npz"
    new_path = BASE / "local/paired-ds8/DS8-F039-v1498-data-soft.npz"
    old, new = np.load(old_path), np.load(new_path)
    old_bins = np.intersect1d(old["bins0"], old["bins1"])
    bins = new["bins0"]
    added = ~np.isin(bins, old_bins)
    frames = receipt["qualified_frames"]
    split = len(frames) // 2
    train, evaluation = frames[:split], frames[split:]
    variable, threshold = select_positions(new["z0"][train, :6])
    x, y = [new[f"z{rx}"][evaluation, :6] for rx in (0, 1)]
    keep = variable[None] & (abs(x.real) / np.maximum(abs(x), 1e-20) >= threshold[None])
    groups = []
    for name, carriers in [("additional", added), ("previously_covered", ~added)]:
        mask = keep & carriers[None, None]
        controls = [
            score(x, np.roll(y, shift, axis=0), mask)["agreement"]
            for shift in range(1, len(evaluation))
        ]
        groups.append(
            dict(
                group=name,
                bins=bins[carriers].tolist(),
                selected_variable_coordinates=int(variable[:, carriers].sum()),
                matched=score(x, y, mask),
                control_mean=float(np.mean(controls)),
                control_max=float(np.max(controls)),
            )
        )
    changes = []
    for rx in (0, 1):
        common, oi, ni = np.intersect1d(old[f"bins{rx}"], bins, return_indices=True)
        oz, nz = old[f"z{rx}"][:, :, oi], new[f"z{rx}"][:, :, ni]
        changes.append(
            dict(
                receiver=rx,
                common_carriers=len(common),
                relative_rms_change=float(np.linalg.norm(nz - oz) / np.linalg.norm(oz)),
            )
        )
    result = dict(
        method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [inventory_path, receipt_path, old_path, new_path]
        },
        aliases=aliases,
        independent_new_recordings=0,
        added_carriers=bins[added].tolist(),
        groups=groups,
        calibration_changes=changes,
    )
    out = BASE / "local/paired-ds8/alias-audit.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
