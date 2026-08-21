"""Compatibility import for the offline Research line-finder API."""

from leo.analysis.cfo_lines import (
    Algorithm,
    CfoPoint,
    DynamicProgrammingConfig,
    HoughConfig,
    LineDetectionConfig,
    LineSegment,
    RansacConfig,
    canonical_points,
    circular_residual_hz,
    dynamic_programming_lines,
    robust_ransac_lines,
    weighted_hough_lines,
    with_common,
)

__all__ = [
    "Algorithm",
    "CfoPoint",
    "DynamicProgrammingConfig",
    "HoughConfig",
    "LineDetectionConfig",
    "LineSegment",
    "RansacConfig",
    "canonical_points",
    "circular_residual_hz",
    "dynamic_programming_lines",
    "robust_ransac_lines",
    "weighted_hough_lines",
    "with_common",
]
