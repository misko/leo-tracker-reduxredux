"""Plot adaptive double-difference phase without bridging retune boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
INPUT = (
    ROOT
    / "reports/figures/2026_09_16_adaptive_dual_rx_phase/adaptive-phase-association-summary.json"
)
OUTPUT = ROOT / "reports/figures/2026_09_23_adaptive_retune_phase_audit"


def wrapped_visit_points(states: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return visit identity, relative time, and wrapped phase without interpolation."""
    visits = np.asarray([row["visit_index"] for row in states], dtype=int)
    time_s = np.asarray([row["time_s"] for row in states], dtype=float)
    phase_deg = np.asarray([row["phase_deg"] for row in states], dtype=float)
    wrapped_deg = np.degrees(np.angle(np.exp(1j * np.radians(phase_deg))))
    return visits, time_s - time_s.min(), wrapped_deg


def main() -> None:
    document = json.loads(INPUT.read_text())
    rows = []
    for session in document:
        for track, states in zip(session["tracks"], session["track_states"], strict=True):
            if len(states) < 3:
                continue
            rows.append((session["session_id"], track, states))
    rows.sort(key=lambda item: (-item[1]["count"], item[0], item[1]["target_index"]))
    selected = rows[:6]
    figure, axes = plt.subplots(3, 2, figsize=(12, 10), layout="constrained")
    output_rows = []
    for axis, (session_id, track, states) in zip(axes.ravel(), selected, strict=True):
        visits, time_s, phase_deg = wrapped_visit_points(states)
        axis.scatter(time_s, phase_deg, c=visits, cmap="viridis", s=30)
        axis.set_title(f"{session_id[-8:]} target {track['target_index']}, n={len(states)}")
        axis.set(
            xlabel="Time from first visit (s)", ylabel="Wrapped DD phase (deg)", ylim=(-185, 185)
        )
        axis.grid(alpha=0.2)
        output_rows.append(
            {
                "session_id": session_id,
                "target_index": track["target_index"],
                "count": len(states),
                "visit_indices": visits.tolist(),
                "retune_boundaries_connected": False,
                "phase_unwrapped_across_visits": False,
            }
        )
    figure.suptitle("Adaptive phase at independent retuned visits — no cross-retune lines")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    figure.savefig(OUTPUT / "wrapped-per-visit-phase.png", dpi=160)
    (OUTPUT / "audit.json").write_text(
        json.dumps(
            {
                "input": str(INPUT.relative_to(ROOT)),
                "selection": "six longest phase-blind associated tracks; display only",
                "rows": output_rows,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
