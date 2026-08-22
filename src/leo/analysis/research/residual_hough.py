"""Compatibility imports for the shared residual-Hough implementation."""

from leo.analysis.residual_hough import (
    ResidualHoughLine,
    ResidualHoughSelection,
    ResidualHoughSelectionConfig,
    detect_all_residual_hough_lines,
    detect_residual_hough_lines,
    select_residual_hough_partition,
)

__all__ = [
    "ResidualHoughLine",
    "ResidualHoughSelection",
    "ResidualHoughSelectionConfig",
    "detect_all_residual_hough_lines",
    "detect_residual_hough_lines",
    "select_residual_hough_partition",
]
