"""Reduce the frozen development pair and the single held 0374 publication."""

from argparse import ArgumentParser
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
PAIR = HERE/"measurements/history-risk-route.json.gz"
PAIR_SHA256 = "11410cc7057f67442f63cdc99b151b4d3686a97c8f27baae168e79d65c8156fe"


def reduction(reference, candidate):
    ratios = [a/b for a, b in zip(reference, candidate, strict=True)]
    return dict(reference_total_s=sum(reference), routed_total_s=sum(candidate),
                summed_ratio=sum(reference)/sum(candidate), median_paired_ratio=median(ratios), paired_ratios=ratios)


def aggregate(earlier, held, held_binding, held_sha256):
    by_case = earlier["enrolled"] | {"0374": dict(result=held, source_stage=held_binding, result_sha256=held_sha256)}
    if list(by_case) != ["0160", "0316", "0374"] or any(row["result"]["case"] != "DS30-"+case for case, row in by_case.items()):
        raise ValueError("Expected the frozen two-case development set and one held DS30-0374 transfer")
    totals = {}
    for name in ("elapsed_s", "cpu_s"):
        charge = "elapsed_ns" if name == "elapsed_s" else "cpu_ns"
        reference = [row["result"]["archive_stock_clock"][name] for row in by_case.values()]
        children = [row["result"]["clock"][name] for row in by_case.values()]
        charged = [price + row["source_stage"]["preflight"][charge]/1e9
                   for price, row in zip(children, by_case.values(), strict=True)]
        totals[name] = dict(child=reduction(reference, children), preflight_charged=reduction(reference, charged))
    return dict(enrolled=by_case, totals=totals, development_receipt_sha256=PAIR_SHA256)


def main(root, output):
    earlier = gzip.decompress(PAIR.read_bytes())
    if sha256(earlier).hexdigest() != PAIR_SHA256:
        raise ValueError("The already sealed development pair changed")
    result_body = (root/"result.json").read_bytes()
    result = json.loads(result_body)
    admission = (root/"route-binding.json").read_bytes()
    if sha256(admission).hexdigest() != result["binds"]["route-binding.json"]:
        raise ValueError("The held comparison must bind its own recorded admission clock")
    joined = aggregate(json.loads(earlier), result, json.loads(admission), sha256(result_body).hexdigest())
    with output.open("x") as stream:
        json.dump(joined, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("transfer", type=Path)
    parser.add_argument("output", type=Path)
    opts = parser.parse_args()
    main(opts.transfer, opts.output)
