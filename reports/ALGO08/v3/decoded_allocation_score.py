"""Check exact signed parity and summarize observed memory and fault scopes."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

from decoded_allocation_trial import MODES, PINNED_PREFIX, TRACE
from continued_cfo_first_0016 import read, write
from empty_bootstrap import checked


INSIDE = "32c61a85609fffbbc4cf23c0c10990f693415fb01593dcac71901de065e6c71d"
OMITTED = "3c096f0b9b2694fc288ca040fc020f647371ef1aa3117baea9617a635f5336c8"
ORIGINAL = Path("/dev/shm/leo-v3-continued-first-0016-result02/1-guarded")
SOUTH = Path("/dev/shm/leo-v3-south-omitted-raw01/result.json")
GROUPS = ("first", "next_seven", "remaining", "all")


def summarize_decode(rows):
    groups = (rows[:1], rows[1:8], rows[8:], rows)
    result = {}
    for name, observed in zip(GROUPS, groups, strict=True):
        fields = ("cpu_ns", "elapsed_ns", "system_cpu_s", "minor_faults", "major_faults", "returned")
        sums = {key: sum(row[key] for row in observed) for key in fields}
        size = sums["returned"]/1024**2
        result[name] = sums | dict(mib=size, storage=dict(Counter(row["storage"] for row in observed)),
                                   minor_faults_per_mib=sums["minor_faults"]/size,
                                   system_cpu_ms_per_mib=1e3*sums["system_cpu_s"]/size)
    return result


def parity(path, prior):
    checked(path/"detections.json", PINNED_PREFIX)
    scope = read(path/"scope-receipt.json")
    exact = ("acquired_probes", "original_probes", "paid", "prefix_inventory", "held_choice", "iq", "opened", "recipe")
    if (any(scope[key] != prior[key] for key in exact) or scope["position_runs"]
            or scope["acquisition"]["native"]["cfo_refinement"]["lanes"]
            != prior["acquisition"]["native"]["cfo_refinement"]["lanes"]):
        raise ValueError("Owned allocator trial changed raw probes or signed tail and route decisions")
    return scope


def south():
    reference = json.loads(gzip.decompress(checked(HERE/"measurements/combined-raw-south.json.gz", INSIDE)))
    omitted = json.loads(checked(SOUTH, OMITTED))
    def clocks(report):
        phases = report["phases"]
        return dict(total=report["clock"], acquire=phases["authenticated_raw_acquisition"],
                    decision_and_publication=phases["decision_and_publication"])

    return dict(containing=clocks(reference), omitted=clocks(omitted),
                delta_minor_faults=omitted["clock"]["minor_faults"]-reference["clock"]["minor_faults"],
                source_sha256=dict(inside=INSIDE, omitted=OMITTED), same_detector=omitted["same_detector"],
                same_owners=omitted["same_owners"])


def score(root):
    binding = read(root/"binding.json")
    for name, pin in binding["sources"].items():
        checked(HERE/name, pin)
    checked(ORIGINAL/"detections.json", PINNED_PREFIX)
    prior = read(ORIGINAL/"scope-receipt.json")
    runs = {}
    for n, modes in enumerate(MODES, 1):
        for mode in modes:
            tag = f"{n}-{mode}"
            path = root/tag
            scope = parity(path, prior)
            trace = read(path/TRACE)
            measured = read(root/(tag+"-clock.json"))
            for name in ("resident_before", "resident_after"):
                cache = measured[name]
                if cache["unavailable"] or cache["observed_members"] != 2 or cache["cached_pages"] != cache["observed_file_pages"]:
                    raise ValueError("Both signed members must remain resident for every child")
            if measured["clock"]["exit_code"] or trace["mode"] != mode:
                raise ValueError("Fresh measured child failed its assigned arm")
            runs[tag] = dict(trace=trace, decode=summarize_decode(trace["reads"][:-1]), measured=measured,
                             acquisition=scope["acquisition"], native_sha256=scope["native_sha256"],
                             held_choice=scope["held_choice"])
    paired_saving = [(runs[f"{i}-stock"]["acquisition"]["acquire"]["cpu_ns"]-
                      runs[f"{i}-heap"]["acquisition"]["acquire"]["cpu_ns"])/1e6 for i in (1, 2)]
    write(root/"result.json", dict(binding_sha256=sha256((root/"binding.json").read_bytes()).hexdigest(),
                                 prior_scope_sha256=sha256((ORIGINAL/"scope-receipt.json").read_bytes()).hexdigest(),
                                 runs=runs, matched_paid_acquisition_savings_ms=paired_saving,
                                 alternate_member_admitted=all(value >= 25 for value in paired_saving),
                                 south=south()))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    score(cli.parse_args().root)
