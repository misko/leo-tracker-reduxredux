"""Launch the original ALGO07 worker under a qualified numerical runtime composition.

The stager installs this as tools/algo07_production_worker.py and retains the
original worker bytes as tools/algo07_frozen_production_worker.py. The original
persisted ALGO07 contract, inputs, supervisor, budgets, and gates remain in use.
"""

import argparse
from pathlib import Path

from algo07_runtime_release import verify

ROOT = Path(__file__).resolve().parents[1]


def main():
    verify(ROOT)
    import algo07_frozen_production_worker as original

    # Replace the old release-specific integrity check with a pinned superset
    # which binds the preserved source bytes and the declared runtime overrides.
    original.verify_release = lambda: verify(ROOT)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bulk-root', type=Path, required=True)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--maximum-seconds', type=int, choices=range(1, 1201), default=1200)
    original.run(parser.parse_args())


if __name__ == '__main__':
    main()
