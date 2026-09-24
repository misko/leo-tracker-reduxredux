"""Freeze the reciprocal RX1-anchored companion to the relaxed RX0 cohort."""

from pathlib import Path

from tools.research.bind_adaptive_relaxed_phase_300s import run

if __name__ == "__main__":
    result = run(
        Path(
            "reports/figures/2026_09_23_scan_glrt_multiplicity/reciprocal-rx1-anchor-binding.json"
        ),
        anchor_receiver=1,
    )
    print(f"rows={len(result['rows'])}")
