"""Measure a hindsight skip schedule on an authenticated installed-v3 prefix."""

import argparse
import json
from pathlib import Path
from time import process_time_ns
from unittest.mock import patch

from aperture_ingress import PREFIX, compare
from aperture_trial import BENCH, DENSE, configuration, inputs, machine, read, write
from continuation_skip import optimum


def historical():
    from anchor_orbit_census import saved_ledger

    here = Path(__file__).resolve().parent
    bindings = read(here / "measurements/anchor-orbit-census.json")["factor_ledgers"]
    result = {}
    for name in ("DS30-0016", "south"):
        folder = BENCH / "integration-shared/pairs" / name / "candidate/fast-scan-automatic-work"
        detections, = folder.glob("*/detections.json")
        rows, _, costs, binding = saved_ledger(BENCH / f"ledger-{name}.json.gz", detections)
        if binding != bindings[name]["binding"]:
            raise ValueError("Historical ledger identity differs")
        result[name] = dict(binding=binding, **optimum(rows, costs))
    return result


def capture(args, before, keep):
    from tools.pipeline_eval.qualification import blind_compact_run as blind

    original = blind.Native
    full_rows = []
    costs = []

    def observed(*constructor):
        receiver = original(*constructor)
        native = receiver.lib.cancellation_factors

        def measure(context, samples, lane, low, high, output):
            index = len(full_rows)
            if before[index]["receiver_id"] != lane:
                raise ValueError("Unexpected native antenna order")
            if not native.argtypes:
                native.restype, native.argtypes = measure.restype, measure.argtypes
            factors = []
            paid = 0
            count = 0
            if keep is None or index in keep:
                start = process_time_ns()
                count = native(context, samples, lane, low, high, output)
                paid = process_time_ns() - start
                for f in output[:count]:
                    factors.append(blind.factor_candidate(f.rank, f.integer, status="complete", offset=f.offset,
                                                          cfo=f.hz, exact=f.exact, control=f.control,
                                                          margin=f.exact - f.control))
            full_rows.append(dict(before[index], candidates=factors))
            costs.append(paid)
            return count

        receiver.lib.cancellation_factors = measure
        return receiver

    with patch.object(blind, "Native", observed):
        receipt = compare(*args, "full", [])
    if len(costs) != len(before):
        raise ValueError("Native hook did not see every admitted lane")
    return receipt, full_rows, costs


def run(out):
    publication, spec = configuration()
    from leo.contracts.digests import canonical_digest

    system = machine()
    if system["cpu"] != [2] or system["nice"] < 15 or any(v != "1" for v in system["threads"].values()):
        raise RuntimeError("Expected one low-priority numerical core")
    old = historical()
    native, archive, offer, _, identity = inputs("DS30-0008")
    before = [row for row in native["source"]["probes"] if row["visit_index"] < PREFIX]
    if canonical_digest(before) != "sha256:3cee5442affabf0c7ad6f8d17281bc5f0ebfdec465e1a4238261fd45d3217c6e":
        raise ValueError("Installed dense prefix differs from earlier frozen publication")
    inventory = read(DENSE.parent / "baseline" / "fast-scan-inputs" / (native["source"]["session_id"] + ".json"))
    args = (publication, spec, native, inventory, archive, offer)
    measured, raw, costs = capture(args, before, None)
    solution = optimum(raw, costs)
    keep = set(solution["kept_indices"])
    runs = []
    for order in (("oracle", "stock"), ("stock", "oracle")):
        for arm in order:
            receipt, factors, clocks = capture(args, before, keep if arm == "oracle" else None)
            for i, row in enumerate(raw):
                expected = [] if arm == "oracle" and i not in keep else row["candidates"]
                if factors[i]["candidates"] != expected:
                    raise ValueError("Paid native waveform factors differ")
            for field in ("window_receipts", "scoped_raw_digest", "probe_sha256", "admitted", "selected"):
                if receipt[field] != measured[field]:
                    raise ValueError(f"Prefix receipt changed: {field}")
            runs.append(dict(arm=arm, native_cpu_ns=sum(clocks), **receipt))
    write(out, dict(machine=system, historical=old, dense=dict(identity=identity, measured=measured,
          full_factor_digest=canonical_digest(raw), optimization_native_cost_ns=costs,
          full_solution=solution, paired_runs=runs)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
