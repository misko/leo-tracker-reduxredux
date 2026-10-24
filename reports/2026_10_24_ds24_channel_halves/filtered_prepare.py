"""Filter physical GLRT winners before graph construction or any numerical fit."""
import argparse
from pathlib import Path
import json
import prepare_algo02_ds23 as prep


def restrict(rows, metadata, channels):
    allowed=set(channels)
    selected=[r for r in rows if r['channel'] in allowed]
    return selected,dict(metadata,channel_subset=sorted(allowed),
                         original_winning_points=len(rows),selected_winning_points=len(selected),
                         channel_filter_before_graph_and_calibration=True)


def main(root,case):
    import evaluate_ds23_phase_refreshed as graph
    channels=json.loads((root/'channels.json').read_text())['channels']
    original=graph.winners
    graph.winners=lambda document:restrict(*original(document),channels)
    try:
        prep.prepare(root,case)
    finally:
        prep.restore_output_owner(root,case)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run-dir',type=Path,required=True);p.add_argument('--case',required=True)
    a=p.parse_args();main(a.run_dir,a.case)
