"""Unchanged numerical audit on independently reconstructed nested evidence ports."""
import argparse
from pathlib import Path
import evaluate_pilot
from evaluate_variant import evaluate
from denser_window_inputs import prepare_denser_window
from screen_seed_prefix import sealed, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    freeze = sealed(args.directory/'sources.json')
    limit = freeze['point_limit']
    unit = freeze['units'][0]['unit_id']
    receipt_path = args.directory/(unit+'.json')
    if receipt_path.exists():
        receipt = sealed(receipt_path)
        parent = Path(freeze['parent_receipt'])
        original = sealed(parent)
        assert receipt['denser_pilot']['parent_sha256'] == digest(parent)
        assert receipt['denser_pilot']['point_limit'] == limit
        assert receipt['denser_pilot']['initial_state'] == original['best']['mean']
        assert receipt['denser_pilot']['max_iterations'] == 64
        _, selection = prepare_denser_window(unit, limit)
        assert selection == receipt['denser_pilot']['selection']
        if limit == 8:
            assert abs(receipt['fits'][0]['objectives'][0]-original['best']['objectives'][-1]) < 1e-6
    evaluate_pilot.prepare_window = lambda name: prepare_denser_window(name, limit)[0]
    evaluate(args.directory)


if __name__ == '__main__':
    main()
