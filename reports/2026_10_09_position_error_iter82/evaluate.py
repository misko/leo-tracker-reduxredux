"""Retry only iteration78 DS17 input failures; numerical evaluator unchanged."""

import argparse
import functools
import hashlib
import json
import runpy
import sys
from pathlib import Path

from protocol_loader import verified_protocol

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ORIGINAL = HERE.parent / "2026_10_09_position_error_iter78"


def main(shard):
    plan = json.loads((HERE / "protocol.json").read_text())
    assert 0 <= shard < plan["shards"]
    for path, expected in plan["source_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
    sys.path.insert(0, str(ORIGINAL))
    namespace = runpy.run_path(str(ORIGINAL / "evaluate.py"), run_name="retry_import")
    baseline = sys.modules["baseline"]
    assert Path(baseline.__file__).resolve() == (
        HERE.parent / "2026_10_08_position_error_iter01/baseline.py"
    )
    baseline.protocol = functools.partial(verified_protocol, baseline.HERE)
    # Only metadata lookup and output destination change. All numerical code is original.
    evaluate = namespace["evaluate"]
    evaluate.__globals__["HERE"] = HERE
    digest = hashlib.sha256((HERE / "protocol.json").read_bytes()).hexdigest()
    for ordinal, binding in enumerate(plan["members"]):
        if ordinal % plan["shards"] == shard:
            path = ORIGINAL / "results" / (binding["member"]["inventory_label"] + ".json")
            original = json.loads(path.read_text())
            assert original["status"] == "failed"
            assert "cannot import name 'digest' from 'freeze'" in original["error"]
            evaluate(binding, plan, digest)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard", type=int, required=True)
    main(parser.parse_args().shard)
