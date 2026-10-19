"""Replay conditional stationary fusion from compact RF-only inputs."""

import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/"source_snapshot"))
from ds23_stationary_consensus import causal_estimates


def run(output):
    document=json.loads((ROOT/"evidence/rf_positions.json").read_text())
    if not document["declared_stationary_research_assumption"]:
        raise ValueError("stationary mode requires an explicit declaration")
    results={method:{a:causal_estimates(rows,method,declared_stationary=True)
        for a,rows in document["records"].items()} for method in ("mean","spatial_median")}
    output.write_text(json.dumps(results,indent=2,allow_nan=False,
        default=lambda value:value.tolist())+"\n")


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--output",type=Path,required=True)
    run(parser.parse_args().output)
