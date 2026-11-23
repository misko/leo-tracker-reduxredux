"""Check the physical and omission screens, then score an eligible dense replay."""

import argparse
import gzip
import json
from pathlib import Path

from aperture_trial import ARMS, read, write
from degree_only_transfer import dense_inputs
from full_short_graph_transfer import inputs
from mixture_score import section
from short_transfer_score import DATA, position, publication


def accepted(arms, decision, far):
    return (decision == "complete" and far == "withheld" and
            all(arms[a]["delta_error_km"] is not None and arms[a]["delta_error_km"] <= .25 for a in ARMS))


def score(case, root, dense_root):
    dense = case == "dense"
    _, _, _, _, pin, offer = dense_inputs(dense_root) if dense else inputs(case)
    result = publication(root, pin, offer)
    if case == "south-far":
        return result
    if dense:
        reference = read(DATA / "dense-control-clocks.json")["common"]
        # The archived astrometric reference is used only after the terminal is sealed.
        pair = read(Path("/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-pair/pair.json"))
        if pair["runs"]["baseline"]["receipt"]["terminal_sha256"] != reference["terminal_sha256"]:
            raise ValueError("Dense stock comparator changed")
        ordinary = pair["runs"]["baseline"]["arms"]
        folder = dense_root / "publication"
        report = read(folder / "joint-research-receipt.json")
        quadratic = read(folder / "fast-scan-automatic-work" / report["receipt"]["run_id"] / "terminal.json")["arms"]
    else:
        original = json.loads(gzip.decompress((DATA / "full-short-DS30-0016-raw.json.gz").read_bytes()))["runs"]
        ordinary, quadratic = [original[k]["verified"]["arms"] for k in ("stock", "candidate")]
    truth = position("DS30-0008" if dense else "DS30-0016")
    result["against_stock"] = section(result["terminal"]["arms"], truth, ordinary)["arms"]
    result["against_quadratic"] = section(result["terminal"]["arms"], truth, quadratic)["arms"]
    return result


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("mode", choices=("screen", "dense"))
    cli.add_argument("prefix", type=Path)
    cli.add_argument("output", type=Path)
    cli.add_argument("--source", type=Path, default=Path("/var/tmp/leo-full-short-dense-DS30-0008"))
    args = cli.parse_args()
    if args.mode == "screen":
        cases = {c: score(c, Path(str(args.prefix) + "-" + c), args.source) for c in ("physical", "south-far")}
        weak, omitted = cases.values()
        result = dict(cases=cases, passed=accepted(weak["against_stock"], weak["decision"], omitted["decision"]))
    else:
        result = score("dense", Path(str(args.prefix) + "-dense"), args.source)
    write(args.output, result)
