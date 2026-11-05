"""Exact complete inclusion/retry comparison and unchanged inventory prefix."""

import argparse
import hashlib
import json
from pathlib import Path


def first_difference(left, right, path="root"):
    if type(left) is not type(right):
        return path + ": type"
    if isinstance(left, dict):
        if set(left) != set(right):
            return path + ": keys " + str(sorted(set(left) ^ set(right)))
        for key in left:
            difference = first_difference(left[key], right[key], path + "." + key)
            if difference:
                return difference
    elif isinstance(left, list):
        if len(left) != len(right):
            return path + ": length"
        for i, (a, b) in enumerate(zip(left, right, strict=True)):
            difference = first_difference(a, b, path + f"[{i}]")
            if difference:
                return difference
    elif left != right:
        return path + f": {left!r} != {right!r}"
    return None


def compare(reference, candidate, earlier_inventory):
    fields = ("predictive_annotation", "predictive_inclusion")
    if set(reference) != set(fields):
        raise ValueError("Incomplete external reference")
    difference = first_difference(reference, {k: candidate[k] for k in fields})
    if difference:
        raise ValueError("Predictive inclusion differs: " + difference)
    difference = first_difference(
        earlier_inventory, {k: v for k, v in candidate.items() if k not in fields}
    )
    if difference:
        raise ValueError("Preceding scientific prefix differs: " + difference)
    return dict(
        exact=True,
        preceding_inventory_exact=True,
        full_pipeline_parity=False,
        scope="Complete annotation, matched control/addition, exact orbit/owner replay, "
        "numerical retry when eligible and scoped adoption, both c arms",
    )


def run(args):
    paths = {k: getattr(args, k) for k in ("reference", "candidate", "earlier_inventory")}
    raw = {k: p.read_bytes() for k, p in paths.items()}
    result = compare(*(json.loads(raw[k]) for k in paths))
    result["inputs"] = {
        k: dict(path=str(paths[k]), sha256=hashlib.sha256(v).hexdigest()) for k, v in raw.items()
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("reference", "candidate", "earlier-inventory", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())
