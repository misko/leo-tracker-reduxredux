"""Use an interval from disjoint subscans for the terminal compact face decision."""

import runpy
from unittest.mock import patch

from tools.pipeline_eval.variants import edge_evidence, edge_interval

if __name__ == "__main__":
    with patch.object(edge_evidence, "evaluate", edge_interval.evaluate):
        runpy.run_path("/trial/held-face.py", run_name="__main__")
