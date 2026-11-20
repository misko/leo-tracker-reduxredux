"""Export the exact four-region queries from the original matched roof comparison."""

import argparse
import json
from pathlib import Path

from .. import corpus
from ..__main__ import references, save_json


def freeze(prototype, destination):
    _, hashes = corpus._selection("roof16")
    inputs = corpus._index(corpus._read_frozen("inputs.jsonl", hashes))
    ids = {r["id"] for p in ("ds26-common127", "roof16") for r in references(p, None)[1]}
    blind = {
        r["recording"]: inputs[r["id"]]
        for r in references("transfer124", None)[1]
        if r["group"] == "DS29" and r["condition"] == "present"
    }
    entries = {}
    for case in sorted(ids):
        single = inputs[case]
        prior = json.loads((prototype / (case + ".json")).read_bytes())
        if (
            prior["case"] != case
            or prior["observation"] != single["observation"]
            or prior["catalog"] != single["catalog"]["sha256"]
            or prior["offers"]["one"] != single["regions"]
        ):
            raise ValueError(f"{case} does not match the original single-region trial")
        if case in blind:
            query = blind[case]
            if (
                query["catalog"] != prior["catalog"]
                or query["observation"] != prior["observation"]
                or query["catalog_timestamp_ns"] != single["catalog_timestamp_ns"]
            ):
                raise ValueError(f"{case} does not match its original blind query")
            regions = query["regions"]
        else:
            regions = prior["offers"]["four"]
        if len(regions) != 4:
            raise ValueError(f"{case} has an incomplete set of region offers")
        entries[case] = dict(
            observation_sha256=prior["observation"],
            catalog_sha256=prior["catalog"],
            regions=regions,
        )
    save_json(destination, entries)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prototype", type=Path, required=True, help="original roof trial directory"
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    freeze(args.prototype, args.out)
