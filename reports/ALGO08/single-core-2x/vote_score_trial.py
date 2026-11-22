"""Replay exact-score demand against complete pre-selection RF ledgers."""

import argparse
import gzip
import json
from collections import Counter
from hashlib import sha256
from pathlib import Path

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.vote_score_recovery import retained_factor

INPUTS = {
    "ledger-DS30-0016.json.gz": "1ef554faa2a490590a13a0de0478baf11036c5292eaabaa0b725b87fa1103336",
    "ledger-south.json.gz": "488290a98cf617cf1f48ea6eb6a5c8b6e1406b41396c93a66d5c1b94fe3ca66f",
}


def replay(ledger, *, reverse):
    history = Continuation()
    published, counts = [], Counter()
    for row in ledger["rows"]:
        exact = list(reversed(row["candidates"])) if reverse else row["candidates"]
        # Present an ordering and margins unrelated to the exact winner.
        approximate = [
            dict(factor, fractional_margin=-factor["fractional_margin"]) for factor in exact
        ]
        _, _, votes = history.select(dict(row, candidates=approximate))

        def recover(index, factors=exact):
            counts["requested"] += 1
            return factors[index]

        retained = retained_factor(votes, recover)
        published.append(dict(row, candidates=[retained] if retained is not None else []))
        counts["always_repair_pairs"] += 2 if len(votes) == 2 else int(retained is not None)
        counts["two_factor_lanes"] += int(len(votes) == 2)
        counts["retained"] += int(retained is not None)
    digest = canonical_digest(published)
    if digest != ledger["ordered_selected_sha256"]:
        raise ValueError("Changed the deployed selected observations")
    return dict(counts, selection_sha256=digest, rows=len(published))


def run(workspace):
    results = {}
    for name, expected in INPUTS.items():
        data = (workspace / name).read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError("Saved factor ledger differs from the frozen input")
        ledger = json.loads(gzip.decompress(data))
        forward, reversed_order = (replay(ledger, reverse=flag) for flag in (False, True))
        if forward != reversed_order:
            raise ValueError("Frequency order affected a vote or a published factor")
        results[name] = dict(forward, input_sha256=expected, raw_authority=ledger["raw_authority"])
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    print(json.dumps(run(parser.parse_args().workspace), indent=2))
