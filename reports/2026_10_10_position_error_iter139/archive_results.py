"""Explicit139 complete raw archive using unchanged reviewed implementation."""

import runpy
from pathlib import Path

from report import prepare

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter133/archive_results.py"))


def create(here=HERE, root=ROOT):
    prepare(here, root)
    return API["create"](here, root)


if __name__ == "__main__":
    create()
