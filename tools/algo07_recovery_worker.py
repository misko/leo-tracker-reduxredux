"""Private-input-only numerical ALGO07 worker, launched under the read guard."""
import argparse
from pathlib import Path
from algo07_science.runner import run_worker

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run_worker('SCAN', args.input.resolve(), args.output.resolve())
