"""Price warmed RF blocks and run the signed solve on their causally reproducible selections."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from aperture_trial import inputs, write
from blind_joint_trial import trial


CASES = ("DS30-0008", "south-containing", "south-far")
KEYS = ("edge", "channel", "actual_rf_hz")


def schedule(probes):
    pairs = list(zip(probes[::2], probes[1::2], strict=True))
    if not pairs:
        raise ValueError("No admitted stereo visits")
    groups = sorted({tuple(first[k] for k in KEYS) for first, _ in pairs})
    slot = {group: i % 3 for i, group in enumerate(groups)}
    history = defaultdict(lambda: deque(maxlen=12))
    keep, paid = set(), set()
    previous_counter = previous_visit = -1
    for i, (left, right) in enumerate(pairs):
        visit = left["visit_index"]
        counter = left["valid_start_counter"]
        if (visit <= previous_visit or counter <= previous_counter or (left["receiver_id"], right["receiver_id"]) != (0, 1)
                or any(left[k] != right[k] for k in (*KEYS, "visit_index", "valid_start_counter"))):
            raise ValueError("Malformed stereo schedule")
        previous_counter, previous_visit = counter, visit
        group = tuple(left[k] for k in KEYS)
        third = int(i >= len(pairs) // 3) + int(i >= (2 * len(pairs)) // 3)
        if slot[group] == third:
            keep.add(visit)
            paid.add(visit)
            paid.update(old for old, when in history[group] if counter - when <= 80_000_000)
        history[group].append((visit, counter))
    return keep, paid, slot


def subset(native):
    from leo.contracts.digests import canonical_digest

    source = native["source"]
    if source["sample_rate_hz"] != 10_000_000:
        raise ValueError("Continuation requires the released 10 MS/s clock")
    original = source["probes"]
    keep, paid, slots = schedule(original)
    rows = [p if p["visit_index"] in keep else dict(p, candidates=[]) for p in original]
    implementation = native["provenance"]["detector_sha256"].removeprefix("sha256:")
    binding = canonical_digest(["cancellation", source["raw_recording_authority_digest"], implementation, rows])
    packet = dict(native, source=dict(source, probes=rows, analysis_manifest_sha256=binding),
                  provenance=dict(native["provenance"], run_id="blind-compact-" + binding[7:39]))
    stats = dict(admitted_visits=len(rows) // 2, used_visits=len(keep), paid_visits=len(paid),
                 warmup_visits=len(paid - keep), group_counts_by_third=sorted(Counter(slots.values()).items()),
                 used_digest=canonical_digest(sorted(keep)), paid_digest=canonical_digest(sorted(paid)),
                 original_factors=sum(len(p["candidates"]) for p in original),
                 retained_factors=sum(len(p["candidates"]) for p in rows), packet_digest=canonical_digest(packet))
    return packet, stats


def run(case, output, *, project=subset):
    from aperture_trial import machine

    system = machine()
    if system["cpu"] != [2] or system["nice"] < 15 or set(system["threads"].values()) != {"1"}:
        raise ValueError("Expected a single low-priority Gauss core")
    bound = {}

    def load():
        native, archive, offer, control, identity = inputs(case)
        packet, stats = project(native)
        derived = dict(identity, original_native_sha256=identity["native_sha256"], native_sha256=stats["packet_digest"])
        bound.update(identity=identity, stats=stats, control=control, derived=derived)
        return packet, archive, offer, control, derived

    path = output.with_suffix(".solver.json")
    start, began = process_time(), perf_counter()
    try:
        trial(case, path, repair=True, signed_finish=True, load_saved_inputs=load)
    except (ValueError, RuntimeError, ArithmeticError, AssertionError) as error:
        if not bound:
            raise
        decision = dict(status="failed", error_type=type(error).__name__, reason=str(error),
                        attempt_cpu_s=process_time() - start, attempt_elapsed_s=perf_counter() - began)
    else:
        result = json.loads(path.read_bytes())
        if result["identity"] != bound["derived"]:
            raise ValueError("Saved solve used a different packet")
        decision = dict(result["result"], charged=result["charged"], roles=result["published_roles"],
                        route=[a["decision"] for a in result["attempts"]],
                        full_solver_receipt_sha256=sha256(path.read_bytes()).hexdigest())
    from leo.contracts.digests import canonical_digest

    write(output, dict(case=case, input=bound["identity"], mask=bound["stats"], stock=bound["control"],
                       decision=decision, machine=system,
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                       sealed_outcome=canonical_digest(decision)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("case", choices=CASES)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    run(args.case, args.output)
