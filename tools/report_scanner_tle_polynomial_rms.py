#!/usr/bin/env python3
"""Generate machine-readable and 3x2 per-track scanner TLE reviews."""

from leo.operations.scanner_tle_review_report import _render_track_plots, build_report, main

__all__ = ["_render_track_plots", "build_report"]


if __name__ == "__main__":
    main()
