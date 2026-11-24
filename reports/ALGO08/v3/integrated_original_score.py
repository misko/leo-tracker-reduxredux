"""Review sealed original trials with schemas normalized to their JSON representation."""

import argparse
import json
from pathlib import Path
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]

# The historical controls add their own checkout to sys.path. Resolve the
# explicitly reviewed snapshot and sparse recipe before loading those controls.
import full_short_run
import legacy_block_raw_score as complete
import legacy_block_0107_score
import legacy_verify_original_trial
import integrated_original_trial as trial


def score(root, case, first=None):
    snapshot = complete.snapshot

    def from_store(*args, **options):
        report = snapshot(*args, **options)
        return dict(report, images=json_value(report["images"]),
                    positions=dict(report["positions"], figures=json_value(report["positions"]["figures"])))

    with patch.object(complete, "snapshot", from_store):
        trial.score(root, case, first)


def json_value(value):
    # Dimensions and DPI from the installed stores arrive as tuples. The
    # independently pinned reference is sealed JSON with corresponding arrays.
    return json.loads(json.dumps(value, allow_nan=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("case", choices=trial.ordinary.CASES)
    parser.add_argument("--first", type=Path)
    args = parser.parse_args()
    score(args.root, args.case, args.first)
