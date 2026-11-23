"""Measure a hindsight skip schedule on an authenticated installed-v3 prefix."""

import argparse
import ctypes as ct
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


def capture(args, before, keep, *, primary=None, first_indices=(), primary_trace=None, expected_rows=None):
    from tools.pipeline_eval.qualification import blind_compact_run as blind

    original = blind.Native
    captured = []
    costs = []
    step = ct.sizeof(blind.Factor)
    if (first_indices or primary_trace is not None) and primary is None:
        raise ValueError("A first-only call requires its native verifier")

    def factors(packet):
        return [blind.Factor.from_buffer_copy(packet, offset) for offset in range(0, len(packet), step)]

    def published(packet):
        return [blind.factor_candidate(f.rank, f.integer, status="complete", offset=f.offset,
                                       cfo=f.hz, exact=f.exact, control=f.control, margin=f.exact - f.control)
                for f in factors(packet)]

    def observed(*constructor):
        receiver = original(*constructor)
        native = receiver.lib.cancellation_factors

        def measure(context, samples, lane, low, high, output):
            index = len(captured)
            if before[index]["receiver_id"] != lane:
                raise ValueError("Unexpected native antenna order")
            if not native.argtypes:
                native.restype, native.argtypes = measure.restype, measure.argtypes

            def call(kernel, out, maximum):
                start = process_time_ns()
                ok = kernel(context, samples, lane, low, high, out)
                cpu = process_time_ns() - start
                if not 0 <= ok <= maximum:
                    raise ValueError("Native call returned an invalid factor count")
                return ok, cpu, ct.string_at(out, ok * step)

            if primary_trace is not None:
                scratch = (blind.Factor * 2)()
                if index % 2:
                    _, primary_cpu, primary_packet = call(primary, scratch, 1)
                    count, paid, packet = call(native, output, 2)
                else:
                    count, paid, packet = call(native, output, 2)
                    _, primary_cpu, primary_packet = call(primary, scratch, 1)
                primary_trace.append((primary_packet, primary_cpu))
            elif index in first_indices:
                count, paid, packet = call(primary, output, 1)
            elif keep is None or index in keep:
                count, paid, packet = call(native, output, 2)
            else:
                count, paid, packet = 0, 0, b""
            captured.append(packet)
            costs.append(paid)
            return count

        receiver.lib.cancellation_factors = measure
        return receiver

    with patch.object(blind, "Native", observed):
        receipt = compare(*args, "full", [], expected_rows=expected_rows)
    if len(costs) != len(before):
        raise ValueError("Native hook did not see every admitted lane")
    if primary_trace is not None:
        for index, ((packet, cpu), full) in enumerate(zip(primary_trace, captured, strict=True)):
            rank_zero = b"".join(bytes(f) for f in factors(full) if f.rank == 0)
            if packet != rank_zero:
                raise ValueError(f"Primary native factor bytes differ at opportunity {index}")
            primary_trace[index] = published(packet), cpu
    full_rows = [dict(row, candidates=published(packet)) for row, packet in zip(before, captured, strict=True)]
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
