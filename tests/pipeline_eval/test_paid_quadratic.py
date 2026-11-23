import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from leo.analysis.polynomial_tracklets import TrackConfig
from paid_quadratic import quadratic


def test_quadratic_caps_degree_and_preserves_doppler_evidence_settings():
    stock = TrackConfig(max_slope_hz_s=8000)
    sparse = quadratic(stock)
    assert asdict(sparse) == dict(asdict(stock), max_degree=2, points_per_coefficient=2, min_points=6)
    assert sparse.min_points - (sparse.max_degree+1) == 3
