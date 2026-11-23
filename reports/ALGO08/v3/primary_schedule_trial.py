"""Measure optimal three-action schedules on the original signed v3 prefix."""

import argparse
import ctypes as ct
from hashlib import sha256
from pathlib import Path
import subprocess

from aperture_ingress import PREFIX
from aperture_trial import BENCH, DENSE, PAYLOAD, configuration, inputs, machine, read, write
from continuation_skip_trial import capture
from primary_owner_census import APERTURE_SHA, canonical_owners, pinned_aperture
from primary_schedule import FULL, PRIMARY, SKIP, optimum, replay_actions


BASE = BENCH / "site-free-mode-pair-pgo/candidate/objects/two_carrier_receiver.c"
BASE_SHA = "4f3326eee5522f02ee05a236f22a41fc1af5bb0f21b6e3fe337711a66226f5f7"
DETECTOR = PAYLOAD / "receiver.so"
DETECTOR_SHA = "2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5"
PROBES_SHA = "sha256:3cee5442affabf0c7ad6f8d17281bc5f0ebfdec465e1a4238261fd45d3217c6e"

FIRST = """
int primary_factors(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                    double lo, double hi, ScanFactor out[2]) {
    if (!r || !out) return -1;
    TimingFirstResult p[2] = {0};
    if (timing_first_detect(r->timing, iq, lane, lo, hi, &p[0])) return -1;
    if (!p[0].confirmation) return 0;
    if (portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;
    TwoCarrierPeak peaks[2];
    return verify_peaks(r, p, peaks, out, 1);
}
"""


def digest(blob):
    return sha256(blob).hexdigest()


def build_primary(work):
    from tools.pipeline_eval.qualification.blind_compact_run import Factor

    archived = BASE.read_bytes()
    if digest(archived) != BASE_SHA or digest(DETECTOR.read_bytes()) != DETECTOR_SHA:
        raise ValueError("The archived detector source or installed binary differs from the protocol")
    source = archived.decode()
    private = source[:source.index("TwoCarrierReceiver *two_carrier_create(")]
    private += source[source.index("static int same_peak("):source.index("static int measure(")]
    work.mkdir()
    cfile = work / "primary.c"
    cfile.write_text(private + FIRST)
    library = work / "primary.so"
    old = Path("/tmp/leo-algo08v2-2x")
    command = ["cc", "-shared", "-fPIC", "-O3", "-std=c11", "-ffp-contract=off", "-fno-math-errno",
               "-fno-strict-aliasing", "-I", old / "native/algo08v2/tools/pipeline_eval/variants",
               "-I", old / "tools/pipeline_eval/variants/experimental", cfile, DETECTOR,
               "-Wl,-z,defs", "-lm", "-o", library]
    subprocess.run(command, check=True)
    helper = ct.CDLL(str(library)).primary_factors
    helper.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double, ct.POINTER(Factor)]
    helper.restype = ct.c_int
    return helper, dict(receiver_sha256=DETECTOR_SHA, archived_source_sha256=BASE_SHA,
                        helper_source_sha256=digest(cfile.read_bytes()), helper_sha256=digest(library.read_bytes()),
                        command=list(map(str, command)))


def owned_opportunities(native, before, identity, expected):
    packet = pinned_aperture()["DS30-0008"]["full"]
    probes = native["source"]["probes"]
    index_in_prefix = {(row["visit_index"], row["receiver_id"]): i for i, row in enumerate(before)}
    partial = {}
    for arm, entries in canonical_owners(native, packet, identity, expected).items():
        retained = {}
        for native_index, owner in entries.items():
            row = probes[native_index]
            index = index_in_prefix.get((row["visit_index"], row["receiver_id"]))
            if index is not None:
                if before[index] != row:
                    raise ValueError("Owned opportunity lacks its unique original exported factor")
                retained[index] = owner
        partial[arm] = retained
    union = set().union(*(set(row) for row in partial.values()))
    return union, dict(aperture_sha256=APERTURE_SHA, full_native_sha256=identity["native_sha256"],
                       owner_digests=packet["owners"], full_owner_rows=packet["associated"],
                       by_arm=partial, union_indices=sorted(union))


def expected_rows(rows, selected):
    return [dict(row, candidates=[] if picked is None else [picked])
            for row, picked in zip(rows, selected, strict=True)]


def run(output, work):
    system = machine()
    if (system["cpu"] != [2] or system["nice"] < 15 or "prio 7" not in system["ionice"]
            or any(value != "1" for value in system["threads"].values())):
        raise RuntimeError("Expected CPU 2 and one low-priority numerical thread")
    publication, spec = configuration()
    from leo.contracts.digests import canonical_digest

    primary, build = build_primary(work)
    native, archive, offer, expected, identity = inputs("DS30-0008")
    before = [row for row in native["source"]["probes"] if row["visit_index"] < PREFIX]
    if canonical_digest(before) != PROBES_SHA:
        raise ValueError("Installed Dense prefix differs from the frozen publication")
    owned, authority = owned_opportunities(native, before, identity, expected)
    inventory = read(DENSE.parent / "baseline/fast-scan-inputs" / (native["source"]["session_id"] + ".json"))
    args = (publication, spec, native, inventory, archive, offer)
    first_trace = []
    measured, full, full_costs = capture(args, before, None, primary=primary, primary_trace=first_trace)
    first, first_costs = zip(*first_trace, strict=True)
    costs = [(0, first_ns, full_ns) for first_ns, full_ns in zip(first_costs, full_costs, strict=True)]
    stock = [FULL] * len(before)
    if expected_rows(before, replay_actions(full, first, stock)) != before:
        raise ValueError("Raw native full factors differ from sealed original continuation")

    schedules = {"strict": optimum(full, first, costs), "owned": optimum(full, first, costs, owned)}
    paired = {}
    for variant, result in schedules.items():
        optimized = result["actions"]
        selected = replay_actions(full, first, optimized)
        candidate = expected_rows(before, selected)
        result["donors_without_selection"] = sum(a != SKIP and point is None
                                                 for a, point in zip(optimized, selected, strict=True))
        result["selected_ranks"] = {rank: sum(p is not None and p["candidate_rank"] == rank for p in selected)
                                    for rank in (0, 1)}
        sample_receipts = []
        for order in ((variant, "stock"), ("stock", variant)):
            for arm in order:
                schedule = stock if arm == "stock" else optimized
                full_indices = {i for i, action in enumerate(schedule) if action == FULL}
                first_indices = {i for i, action in enumerate(schedule) if action == PRIMARY}
                receipt, factors, clocks = capture(
                    args, before, full_indices, primary=primary, first_indices=first_indices,
                    expected_rows=before if arm == "stock" else candidate,
                )
                for i, row in enumerate(factors):
                    target = ([], first[i], full[i]["candidates"])[schedule[i]]
                    if row["candidates"] != target:
                        raise ValueError(f"Paid native factors changed at opportunity {i}")
                for k in ("window_receipts", "scoped_raw_digest", "admitted", "compressed_bytes"):
                    if receipt[k] != measured[k]:
                        raise ValueError(f"Prefix integrity changed: {k}")
                if arm != "owned" and receipt["probe_sha256"] != measured["probe_sha256"]:
                    raise ValueError("Strict prefix detections changed")
                sample_receipts.append(dict(arm=arm, native_cpu_ns=sum(clocks), **receipt))
        paired[variant] = sample_receipts
    ledger = [dict(index=i, metadata=dict(row, candidates=[]), full=row["candidates"],
                   primary=first[i], native_cpu_ns=costs[i]) for i, row in enumerate(full)]
    write(output, dict(machine=system, helper=build, identity=identity, ownership=authority,
                    factor_digest=canonical_digest(full), primary_trace_digest=canonical_digest(first),
                    original_probe_sha256=PROBES_SHA, costs_and_factors=ledger, schedules=schedules,
                    cost_census=measured, paired=paired))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=lambda value: Path(value).resolve())
    parser.add_argument("work", type=lambda value: Path(value).resolve())
    run(**vars(parser.parse_args()))
