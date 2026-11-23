"""Compare the two saved likelihood paths and retain their paid costs."""

import argparse
from hashlib import sha256
import json
from pathlib import Path


TIMERS = {
    "cpu_s", "elapsed_s", "endpoint_cpu_s", "gram_or_check_cpu_ns",
    "predictive_kernel_cpu_ns", "curved_cpu_ns", "shifted_cpu_s", "pack_ns",
    "search_ns", "normal_selection_ns", "history_selection_ns", "direct_assembly_ns",
}


def science(result):
    if isinstance(result, dict):
        return {k: science(v) for k, v in result.items() if k not in TIMERS}
    if isinstance(result, list):
        return [science(v) for v in result]
    return result


def checked_pair(stock, candidate):
    if (stock["mode"] != "stock" or candidate["mode"] != "certificate"
            or not all(all(row["checks"].values()) for row in (stock, candidate))
            or stock["compiled"].keys() != candidate["compiled"].keys()):
        raise ValueError("The two complete verified modes are required")
    same = {key: stock[key] == candidate[key]
            for key in ("case", "input_sha256", "cold", "proof", "bound", "checks", "code")}
    same["science"] = science(stock["result"]) == science(candidate["result"])
    same["layout_fallbacks"] = stock["counts"]["fallback"] == candidate["counts"]["fallback"]
    totals, kernels = {}, {}
    for labelled, record in (("stock", stock), ("certificate", candidate)):
        counts = record["counts"]
        totals[labelled] = dict(solver_cpu_s=record["clocks"]["solver_cpu_ns"]/1e9,
                                solver_elapsed_s=record["result"]["elapsed_s"])
        for name in ("ordinary", "grid"):
            kernels.setdefault(name, {})[labelled] = counts[name]
    for name, pair in kernels.items():
        a, b = pair["stock"], pair["certificate"]
        totals["stock"][name+"_cpu_s"] = a["native_cpu_ns"]/1e9
        totals["certificate"][name+"_cpu_s"] = b["native_cpu_ns"]/1e9
        same[name+"_status_counts"] = all(a.get(key) == b.get(key) for key in a.keys() | b.keys()
            if key.startswith("status_") or key in {"calls", "condition_calls", "reject_calls"})
        if a["skip_calls"] or b["skip_calls"] > b["condition_calls"]:
            raise ValueError("Impossible conditioning counts")
    if not all(same.values()):
        raise ValueError(f"The archived exact science or native call inventory drifted: {same}")
    saved = {key: totals["stock"][key]-totals["certificate"][key] for key in totals["stock"]}
    return dict(exact=same, native=kernels, totals=totals, saving=saved,
                bounds=stock["bound"], arms=stock["result"]["arms"],
                input_sha256=stock["input_sha256"])


def run(root, output):
    cases = {}
    for case in ("dense", "weak"):
        paths = [root / f"{case}-{mode}" / "receipt.json" for mode in ("stock", "certificate")]
        sources = [path.read_bytes() for path in paths]
        cases[case] = checked_pair(*(json.loads(value) for value in sources))
        cases[case]["receipts_sha256"] = [sha256(value).hexdigest() for value in sources]
    with output.open("x") as stream:
        json.dump(cases, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("output", type=Path)
    run(**vars(cli.parse_args()))
