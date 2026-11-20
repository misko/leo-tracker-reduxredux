"""Add the paired terminal interior requirement to the sealed recovery worker."""

import runpy
from unittest.mock import patch

from tools.pipeline_eval.variants import portable_v5
from tools.pipeline_eval.variants.compact_tile_interior import guard

original = portable_v5.run


def run(document, *, tile, **kwargs):
    return guard(original(document, tile=tile, **kwargs), tile)


if __name__ == "__main__":
    with patch.object(portable_v5, "run", run):
        runpy.run_path("/trial/main.py", run_name="__main__")
