"""Reuse reviewed133 deterministic all-member archive; no inference or reference read."""

import runpy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter133/archive_results.py"))


def create(here=HERE, root=ROOT):
    return API["create"](here, root)


if __name__ == "__main__":
    create()
