"""Original numerical audit with independently reconstructed discrepancy mapping."""
import argparse
from pathlib import Path
import evaluate_pilot
from evaluate_variant import evaluate
from discrepancy_window_inputs import prepare_discrepancy_window,initial_state
from screen_seed_prefix import sealed,digest


def main():
    parser=argparse.ArgumentParser();parser.add_argument('directory',type=Path);args=parser.parse_args()
    freeze=sealed(args.directory/'sources.json');arm=freeze['discrepancy_arm'];unit=freeze['units'][0]['unit_id']
    parent=Path(freeze['parent_receipt']);original=sealed(parent)
    expected=initial_state(original,arm).tolist()
    assert freeze['initial_state']==expected
    prepared=prepare_discrepancy_window(unit,arm)
    assert freeze['precision']==prepared[3].tolist()
    path=args.directory/(unit+'.json')
    if path.exists():
        receipt=sealed(path);meta=receipt['discrepancy_pilot']
        assert meta['arm']==arm and meta['parent_sha256']==digest(parent)
        assert meta['initial_state']==expected and meta['max_iterations']==64
        assert meta['sigma_km']==(0. if arm=='baseline' else 1.)
        assert meta['base_dimension']==len(original['precision'])
    evaluate_pilot.prepare_window=lambda name:prepare_discrepancy_window(name,arm)
    evaluate(args.directory)


if __name__=='__main__':main()
