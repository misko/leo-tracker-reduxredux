"""Archive all terminal audit receipts with verified bytes; preserve originals."""

import runpy
from pathlib import Path

from report import load

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
API = runpy.run_path(str(HERE.parent / "2026_10_10_position_error_iter133/archive_results.py"))


def create(here=HERE, root=ROOT):
    load(here, root)
    return API["create"](here, root)


if __name__ == "__main__":
    create()
