"""Unchanged numerical audit on independently reconstructed nested evidence ports."""
import argparse
from pathlib import Path
import evaluate_pilot
from evaluate_variant import evaluate
from covariance_track_ports import prepare_covariance_window
from screen_seed_prefix import sealed, digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    freeze = sealed(args.directory/'sources.json')
    limit = freeze['covariance_arm']
    unit = freeze['units'][0]['unit_id']
    receipt_path = args.directory/(unit+'.json')
    if receipt_path.exists():
        receipt = sealed(receipt_path)
        parent = Path(freeze['parent_receipt'])
        original = sealed(parent)
        assert receipt['covariance_pilot']['parent_sha256'] == digest(parent)
        assert receipt['covariance_pilot']['covariance_arm'] == limit
        assert receipt['covariance_pilot']['initial_state'] == original['best']['mean']
        assert receipt['covariance_pilot']['max_iterations'] == 64
        _, selection = prepare_covariance_window(unit, limit)
        assert selection == receipt['covariance_pilot']['selection']
    evaluate_pilot.prepare_window = lambda name: prepare_covariance_window(name, limit)[0]
    evaluate(args.directory)


if __name__ == '__main__':
    main()
