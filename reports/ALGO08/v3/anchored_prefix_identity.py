"""Check the unchanged guarded short and tail 32-anchor rows for reuse."""

import argparse
from collections import Counter
from contextlib import ExitStack
import ctypes as ct
from hashlib import sha256
import json
from pathlib import Path
import struct

import numpy as np

from . import short_prefix_correlations as prefix
from . import short_cfo_refine as ref


PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")
PACK_SHA = "0d590b0c7e4ffc468fb17804146362b8534d33d115d83055ae7bbc1dafd967a9"
SHORT_SHA = "f20605e5a4e487d13548411b0430ea262b9b9c6fba89dae973313d3d0008bb6a"
TAIL_SHA = "304cb40f0577b972eedd582c3aac39ee3cc24af1cd488b0fb9bbd6b3336da7ae"
MEMBER = Path("/dev/shm/leo-anchored-cfo-stage-results01")
MEMBER_SHA = "8b7b9aaf1c914d2ec9e6ac9b1c993533da7599a25dcf5a0743650513452c70a8"
OBSERVER = Path("/dev/shm/leo-v3-prefix-refine-results-02/full/tail.so")
OBSERVER_SHA = "6f007dfe0f92706f1fdd41fae89e5821ab98f646de1e337e0e73139072d8cd28"


class Event(ct.Structure):
    _fields_ = [("epoch", ct.c_uint), ("flags", ct.c_uint)] + [
        (name, ct.c_double) for name in ("frequency", "offset", "residual", "exact", "control")]


def transferable(seed, frequency, accepted_recurrence, tail_retries, near_band):
    return (bool(accepted_recurrence) and struct.pack("=d", seed) == struct.pack("=d", frequency)
            and not tail_retries and not near_band)


def run(output):
    machine = ref.check_machine()
    if output.resolve().parent != Path("/dev/shm"):
        raise ValueError("Use tmpfs for the bounded staged-row result")
    ref.verified(PACK/"pack.json", PACK_SHA)
    for path, pin in ((PACK/"short.so", SHORT_SHA), (PACK/"tail.so", TAIL_SHA), (OBSERVER, OBSERVER_SHA)):
        ref.verified(path, pin)
    base = ref.load(MEMBER/"receipt.json", MEMBER_SHA)
    archived = base["arms"][1]["receipt"]
    sealed = ref.load(MEMBER/"1-anchored/detections.json", archived["native_sha256"][7:])
    trials = {(x["visit"], x["lane"]): x["factors"] for x in archived["vectors"] if x["mode"] == "short_primary"}
    published = {(r["visit_index"], r["receiver_id"]): r["candidates"] for r in sealed["source"]["probes"]}
    assignment = ref.load(ref.HELD/"scope.json", ref.PINS["held_scope"])
    segment = Path(assignment["entry"]["path"])
    if segment.parent != ref.HELD or segment.resolve(strict=True) != segment:
        raise ValueError("The held source escaped its private staged directory")
    names = ("manifest.json", assignment["member"]["payload_relative_path"], assignment["member"]["index_relative_path"])
    for name in names:
        path = segment/name
        if path.resolve(strict=True) != path or path.stat().st_dev != output.parent.stat().st_dev:
            raise ValueError("Only the existing tmpfs member and signed index may be opened")
    before = ref.input_bytes()
    staged, scope = ref.signed_rows("held-0169")
    staged_worker_input_bytes = ref.input_bytes()-before
    auditor = prefix.Audit(OBSERVER)
    tail = prefix.exact.RefineEntry(PACK/"tail.so", "short_cfo_reanchored")
    exact = prefix.exact.RefineEntry(OBSERVER, "short_cfo_refine")
    take_tail = prefix.signature(tail.library, "anchored_take_tail_retries", (), ct.c_uint64)
    events, stats = (Event*8)(), (ct.c_uint64*2)()
    counters, witness = Counter(), []
    asset = np.frombuffer(ref.verified(ref.RELEASE/"assets/lower.f32", ref.PILOT_SHA["lower"]), dtype="<f4")
    with ExitStack() as stack:
        short = ref.NativePath(PACK/"short.so", asset, "short_primary")
        full = ref.NativePath(ref.PAYLOAD/"receiver.so", asset, "full")
        stack.callback(short.close)
        stack.callback(full.close)
        take = prefix.signature(short.native.lib, "anchored_take_audit", (ct.POINTER(Event), ct.POINTER(ct.c_uint64)), ct.c_int)
        for row in staged:
            if row["mode"] != "short_primary" or row["edge"] != "lower":
                continue
            key = row["key"], row["lane"]
            measured, _ = short.run(row["iq"], row["lane"], row["tune"])
            if ref.factor_bytes(measured) != ref.factor_bytes(trials.pop(key)):
                raise ValueError("The untouched B short detector differs from its sealed native vectors")
            calls = take(events, stats)
            if not measured:
                counters["empty"] += 1
                continue
            (factor,) = measured
            epoch, offset, frequency = factor[1:4]
            if calls != 1 or events[0].epoch != epoch or events[0].offset != offset:
                raise ValueError("The retained short state does not uniquely identify this factor")
            seed = events[0].frequency
            first_rows, states = auditor.rows(short, prefix.PREFIX)
            if (states[1] > 0.) != bool(stats[1]):
                raise ValueError("Short acceptance does not match its native recurrence guard")

            starts, _, _ = prefix.frame_geometry(epoch, offset)
            advanced = tail.diagnostics(full, row["iq"], row["lane"], measured)
            tail_retries = take_tail()
            full_rows, _ = auditor.rows(full, len(starts))
            near_band = advanced is not None and abs(abs(frequency+advanced[0]-row["tune"])-800_000) < .001
            if near_band:
                advanced = exact.diagnostics(full, row["iq"], row["lane"], measured)
            final, reason = ref.amend(measured, advanced, 1., row["tune"])
            (factor,) = final
            (emitted,) = published[key]
            fields = ("candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
                      "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score")
            if ref.factor_bytes(final) != ref.factor_bytes((tuple(emitted[k] for k in fields),)):
                raise ValueError("B's own original full tail behaviour differs from the sealed member")
            joined = prefix.same_bytes_by_frame(first_rows, full_rows[:, :prefix.PREFIX])
            usable = transferable(seed, frequency, stats[1], tail_retries, near_band)
            if usable and not all(joined):
                raise ValueError("Guarded recurrence at the same CFO did not preserve its native correlation rows")
            counters.update(positives=1, same_cfo=int(seed == frequency), short_recurrence=int(stats[1]),
                            tail_retries=tail_retries, signed_band_retries=int(near_band), candidate_compatible=int(usable),
                            all_same_rows=int(all(joined)))
            witness.append(dict(visit=key[0], lane=key[1], seed=seed, frequency=frequency, epoch=epoch, offset=offset,
                                short_recurrence=bool(stats[1]), long_exact_retry=bool(tail_retries), near_band=near_band,
                                rows_identical=joined, applicable=usable, original_tail_reason=reason))
    if trials:
        raise ValueError("The held non-anchor denominator changed")
    ref.save(output, dict(machine=machine, scope=scope, counts=counters, rows=witness, source_sha256=sha256(
        Path(__file__).read_bytes()).hexdigest(), reference_sha256=MEMBER_SHA, anchored_pack_sha256=PACK_SHA,
        shorter_sha256=SHORT_SHA, independent_tail_sha256=TAIL_SHA, observer_sha256=OBSERVER_SHA,
        timings_measured=False, decoded_original_staged_member_only=True,
        process_storage_read_bytes_during_intake=staged_worker_input_bytes))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
