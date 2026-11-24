"""Append one verified saved transfer to the frozen history-risk cohort."""

from argparse import ArgumentParser
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


HERE = Path(__file__).resolve().parent
PAIR = HERE/"measurements/history-risk-route.json.gz"
PAIR_SHA256 = "11410cc7057f67442f63cdc99b151b4d3686a97c8f27baae168e79d65c8156fe"
THREE_CASE = HERE/"measurements/history-risk-three-case.json.gz"
THREE_CASE_SHA256 = "b461931fba8c5bbb853966e9d4977bc9d6377393830067780fc36a37be556717"
FOUR_CASE = HERE/"measurements/history-risk-four-case.json.gz"
FOUR_CASE_SHA256 = "2b7cf61aaabe5aa89ff5396376e229603cb9349dd49d3e37776994b5d2740278"
PREDECESSORS = {
    "0374": (PAIR, PAIR_SHA256, ("0160", "0316")),
    "0402": (THREE_CASE, THREE_CASE_SHA256, ("0160", "0316", "0374")),
    "0169": (FOUR_CASE, FOUR_CASE_SHA256, ("0160", "0316", "0374", "0402")),
}


def read_sealed_panel(size):
    path, expected = {3: (THREE_CASE, THREE_CASE_SHA256), 4: (FOUR_CASE, FOUR_CASE_SHA256)}[size]
    content = gzip.decompress(path.read_bytes())
    if sha256(content).hexdigest() != expected:
        raise ValueError(f"Unexpected {size}-recording routed panel")
    return json.loads(content)


def reduction(reference, candidate):
    ratios = [a/b for a, b in zip(reference, candidate, strict=True)]
    return dict(reference_total_s=sum(reference), routed_total_s=sum(candidate),
                summed_ratio=sum(reference)/sum(candidate), median_paired_ratio=median(ratios), paired_ratios=ratios)


def aggregate(earlier, held, held_binding, held_sha256, *, case="0374"):
    _, predecessor_sha, roster = PREDECESSORS[case]
    if tuple(earlier["enrolled"]) != roster or held["case"] != "DS30-"+case:
        raise ValueError("Expected the frozen earlier cohort and the single assigned transfer")
    by_case = earlier["enrolled"] | {case: dict(result=held, source_stage=held_binding, result_sha256=held_sha256)}
    if any(row["result"]["case"] != "DS30-"+key for key, row in by_case.items()):
        raise ValueError("A saved publication does not match its enrolled case")
    totals = {}
    for name in ("elapsed_s", "cpu_s"):
        charge = "elapsed_ns" if name == "elapsed_s" else "cpu_ns"
        reference = [row["result"]["archive_stock_clock"][name] for row in by_case.values()]
        children = [row["result"]["clock"][name] for row in by_case.values()]
        charged = [price + row["source_stage"]["preflight"][charge]/1e9
                   for price, row in zip(children, by_case.values(), strict=True)]
        totals[name] = dict(child=reduction(reference, children), preflight_charged=reduction(reference, charged))
    key = "development_receipt_sha256" if case == "0374" else "prior_panel_receipt_sha256"
    if case == "0169" and not all(row["result"]["named_parity"]["complete"] for row in by_case.values()):
        raise ValueError("The five-positive cohort requires a completed named and routed publication for every case")
    order = {"case_order": list(by_case)} if case == "0169" else {}
    return dict(enrolled=by_case, totals=totals) | {key: predecessor_sha} | order


def main(root, output, *, case="0374"):
    path, digest, _ = PREDECESSORS[case]
    earlier = gzip.decompress(path.read_bytes())
    if sha256(earlier).hexdigest() != digest:
        raise ValueError("The already sealed cohort changed")
    result_body = (root/"result.json").read_bytes()
    result = json.loads(result_body)
    admission = (root/"route-binding.json").read_bytes()
    if sha256(admission).hexdigest() != result["binds"]["route-binding.json"]:
        raise ValueError("The held comparison must bind its own recorded admission clock")
    joined = aggregate(json.loads(earlier), result, json.loads(admission), sha256(result_body).hexdigest(), case=case)
    with output.open("x") as stream:
        json.dump(joined, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("transfer", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--case", choices=PREDECESSORS, default="0374")
    opts = parser.parse_args()
    main(opts.transfer, opts.output, case=opts.case)
