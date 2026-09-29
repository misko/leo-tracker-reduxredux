"""Whole-training-track hard cones for fixed-position scoring only."""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "2026_09_29_cone_trend"))
from cone_trend import ConeTrendPosition  # noqa: E402


class HardConeScore(ConeTrendPosition):
    def log_geometry(self, track, local):
        if self.half_angle_deg is None:
            return super().log_geometry(track, local)
        worst = self.angles(track, local)[:, track["mask"]].max(axis=1)
        return np.where(worst <= self.half_angle_deg, 0.0, -np.inf)

    def evaluate(self, x, gradient=False, held=False):
        if gradient:
            raise ValueError("Hard-gate scoring has no smooth-gradient optimization interface")
        return super().evaluate(x, gradient=False, held=held)
