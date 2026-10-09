"""Load frozen, qualified research components without executing experiments."""

import runpy
import sys
from pathlib import Path

REPORTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPORTS / "2026_10_09_position_error_iter84"))
ENV = runpy.run_path(
    str(REPORTS / "2026_10_09_position_error_iter84/evaluate.py"), run_name="import_only"
)
sys.path.insert(0, str(REPORTS / "2026_10_08_position_error_iter50"))
from dynamic_rf import DynamicRFObjective  # noqa: E402,F401
from dynamic_rf import fit as rf_fit  # noqa: E402,F401
from region_pipeline import (  # noqa: E402,F401
    InitialClockObjective,
    JointClockObjective,
    initial_fit,
    reduce_bank,
    select_documents,
)
from region_pipeline import fit as timing_fit  # noqa: E402,F401

SlopePrior = ENV["SlopePrior"]
load = ENV["load"]
read = ENV["read"]
Hard60Objective = ENV["Hard60Objective"]
HARD60_SCORE = ENV["HARD60_SCORE"]
error_km = ENV["error_km"]
json_value = ENV["json_value"]
arm_selected = ENV["arm_selected"]
