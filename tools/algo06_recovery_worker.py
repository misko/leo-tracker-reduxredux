"""Run the frozen residual-family experiment inside the production read guard."""
import argparse
from pathlib import Path

def run(root, policy):
    from algo06_science import common
    common.configure(root, policy)
    from algo06_science import screen, position
    screen.preflight('SCAN')
    screen.one('SCAN')
    position.one('SCAN')

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--policy', required=True)
    args = p.parse_args()
    run(args.output, args.policy)
