"""Measure and audit exact causal TLE representations on saved detections."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from leo.application.localization_v3_engine import _json_value
from leo.contracts.algo08_region import Algo08Region
from leo.operations.tle_archive import TleArchiveReader
from solver_trial import measure
from tools import algo08_position
from tools.pipeline_eval.variants.algo08_causal_table import causal_table


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("control", "exports", "priors", "table"))
    for name in ("native", "archive", "assets", "region"):
        parser.add_argument(name, type=Path)
    parser.add_argument("native_sha256")
    parser.add_argument("--record-parser", type=Path)
    args = parser.parse_args()
    raw = args.native.read_bytes()
    if sha256(raw).hexdigest() != args.native_sha256.removeprefix("sha256:"):
        raise ValueError("Native detections differ from their declared digest")
    offer = Algo08Region.parse(json.loads(args.region.read_bytes()))
    original = algo08_position.prepare_native_scan
    selected = {}

    def prepare(*args, **kwargs):
        prepared = original(*args, **kwargs)
        selected.clear()
        if prepared["status"] == "inputs_prepared":
            selected.update(phase_history=prepared["phase_history"],
                            phase_forecast=prepared["phase_forecast"])
            selected.update({name: value for name, value in prepared["sky"].items() if name != "bank"})
        return prepared

    parser_scope = nullcontext({})
    if args.record_parser is not None:
        from tools.pipeline_eval.variants.experimental.tle_records import batch_records
        parser_scope = batch_records(args.record_parser)
    with (
        parser_scope as parser_counts,
        causal_table(canonical_exports=args.mode in ("exports", "table"),
                     previous_catalogues=args.mode in ("priors", "table")) as counters,
        patch.object(algo08_position, "prepare_native_scan", prepare),
    ):
        result = measure("combined", json.loads(raw), TleArchiveReader(args.archive), args.assets, offer)
    hashes = {key: sha256(json.dumps(value, default=_json_value, sort_keys=True).encode()).hexdigest()
              for key, value in sorted(selected.items())}
    result.update(mode=args.mode, table_counters=counters, preparation_sha256=hashes,
                  native_sha256=args.native_sha256, region=offer.document())
    if args.record_parser is not None:
        result["record_parser"] = dict(counts=parser_counts, sha256=sha256(args.record_parser.read_bytes()).hexdigest())
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
