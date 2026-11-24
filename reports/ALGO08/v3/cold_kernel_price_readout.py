"""Seal the disjoint timing scopes of both saved cold-stage observations."""

import argparse
from collections import defaultdict
import gzip
from hashlib import sha256
import json
from pathlib import Path


def price(audit):
    pairs = list(zip(audit["probe_rows"], audit["native_calls"], strict=True))
    if not audit["matched_archived_cold_trace"] or any(
        request["kernel_cpu_ns"] != call["native_cpu_ns"] or call["status"] != 0
        for request, call in pairs
    ):
        raise ValueError("Need exact archived parity and one native Gamma call per original calculation")
    by_model = defaultdict(list)
    for request, call in pairs:
        by_model[request["model"]].append((request, call))
    # The pinned first three model identities are finalist prefixes/resumptions.
    # The next three are the same ordered finalists with refreshed phase references.
    trace = audit["trace"]["completed"]
    original_evaluations = [row[field] for field in ("first_evaluations", "second_evaluations") for row in trace]
    endpoints, objective = [], []
    for index, evaluations in enumerate(original_evaluations):
        rows = by_model[index]
        if len(rows) != evaluations + 1 or not rows[-1][0]["exact_repeat"]:
            raise ValueError("Expected one original post-optimizer endpoint calculation")
        objective.extend(rows[:-1])
        endpoints.append(rows[-1])
    if len(endpoints) + len(objective) != len(pairs):
        raise ValueError("Unknown calculation scope")
    derivatives = [(r, c) for r, c in pairs if "axis" in r]
    reused = [(r, c) for r, c in pairs if r["exact_repeat"]]
    static_phases = ("setup", "group_gram", "prior_initialization")
    return dict(
        original_objective_evaluations=len(objective),
        post_optimizer_endpoint_calculations=len(endpoints),
        post_optimizer_endpoint_cpu_ns=sum(row["stock_equivalent_cpu_ns"] for row, _ in endpoints),
        optimizer_whole_repeat_cpu_ceiling_ns=sum(
            row["stock_equivalent_cpu_ns"] for row, _ in objective if row["exact_repeat"]),
        derivative_outside_bound_cpu_ns=sum(
            row["stock_equivalent_cpu_ns"]-call["observed_bound_cpu_ns"]+call["shadow_cpu_ns"]
            for row, call in derivatives),
        derivative_initial_gamma_cpu_ns=sum(
            sum(call["phases"][phase] for phase in static_phases) for _, call in derivatives),
        residual_energy_already_in_repeated_calculations_cpu_ns=sum(
            call["phases"]["residual_energy"] for _, call in reused),
        residual_energy_after_whole_repeat_removal_cpu_ns=sum(
            call["phases"]["residual_energy"] for row, call in pairs if not row["exact_repeat"]),
        successful_robust_updates=sum(call["iterations"] for _, call in pairs),
    )


def seal(output, roots, failure=None):
    observations = {}
    for root in roots:
        files = {filename: (root / filename).read_bytes() for filename in ("audit.json", "binding.json", "clock.json")}
        digests = {name: sha256(data).hexdigest() for name, data in files.items()}
        for name in ("diagnostic.so", "diagnostic.c"):
            digests[name] = sha256((root / name).read_bytes()).hexdigest()
        audit, binding, clock = (json.loads(data) for data in files.values())
        case = binding["case"]
        if case in observations or clock["timing"]["exit_code"] != 0:
            raise ValueError("Expected independently successful signed observation roots")
        observations[case] = dict(directory=str(root), sha256=digests, audit=audit, binding=binding,
                                  through_cutoff=clock, derived=price(audit))
    if set(observations) != {"DS30-0402", "DS30-0374"}:
        raise ValueError("The frozen two-case observation is incomplete")
    failed_start = json.loads((failure / "clock.json").read_bytes()) if failure is not None else None
    record = dict(scope="current cold finalists until winner selection", observations=observations,
                  earlier_worker_failure=failed_start, no_waveform=True)
    with output.open("xb") as stream:
        stream.write(gzip.compress(json.dumps(record, sort_keys=True, allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("roots", nargs=2, type=Path)
    parser.add_argument("--failure", type=Path)
    args = parser.parse_args()
    seal(args.output, args.roots, args.failure)
