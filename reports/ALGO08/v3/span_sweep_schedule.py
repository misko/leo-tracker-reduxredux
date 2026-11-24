"""Price a nested span-first schedule using sealed physical detector ledgers."""

import argparse
from collections import Counter, defaultdict, deque
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter, process_time

from tools.pipeline_eval.variants import carrier_continuation
from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs
from whole_stereo_blocks import (
    CONTINUATION_SHA, DENSE, HERE, NATIVE_SHA, RAW_SHA, RECEIVER_SHA, REQUEST_SHA,
    WEAK, WEAK_CONTROL_SHA, WEAK_RAW, WEAK_RAW_SHA, StereoBlocks, load_checked,
    signature,
)


BLOCK = 64
CHANNELS = 8
# Pinned by authenticated-input-coverage.md and the original compared receipts.
ORIGINAL = {
    "DS30-0008": {
        "layout": (106, 8_182_000_357, 18_300_670, 92_328, 10_835_200_000),
        "publication": Path("/var/tmp/leo-v3-regional-dense-pair/native"),
        "owners_sha256": "11c554cbcca4f756e07e810bbc7b34b548a799fd005645fd4d9e5fcbba8ef72e",
    },
    "DS30-0016": {
        "layout": (13, 991_734_597, 2_186_848, 12_236, 1_292_800_000),
        "publication": WEAK.parent / "weak/installed",
        "owners_sha256": "e96fbfd7283dadf675a8db58cae0c33c799c7354f205b237afd7756a559f5883",
    },
}


def span_order(blocks):
    """Split the largest remaining issued-time gap, with earlier ties first."""
    order = [0] if blocks else []
    if blocks > 1:
        order.append(blocks - 1)
    while len(order) < blocks:
        visited = sorted(order)
        left, right = max(zip(visited, visited[1:]), key=lambda edge: edge[1] - edge[0])
        order.append((left + right) // 2)
    return order


def plan(metadata, issued, *, width=BLOCK):
    """Rows contain visit, channel, actual RF, hardware counter and original aperture."""
    rf_by_channel, previous = {}, defaultdict(lambda: deque(maxlen=12))
    visit_ids, anchors, context = set(), set(), {}
    prior = -1
    for visit, channel, rf, counter, mode in metadata:
        if (not prior < visit < issued or channel != visit % CHANNELS + 1
                or rf_by_channel.setdefault(channel, rf) != rf):
            raise ValueError("Expected a complete issued-index ledger on the original eight-channel sweep")
        prior = visit
        visit_ids.add(visit)
        lane = previous[channel, rf]
        if lane and lane[-1][1] >= counter:
            raise ValueError("The counter must increase within each physical RF stream")
        context[visit] = {other for other, then in lane if counter - then <= 80_000_000}
        lane.append((visit, counter))
        if mode == "full":
            anchors.add(visit)
    if set(rf_by_channel) != set(range(1, CHANNELS + 1)) or width % CHANNELS:
        raise ValueError("The block rule requires a complete original RF sweep")

    def stage(core_blocks, tail):
        core = {visit for visit in visit_ids if visit // width in core_blocks or visit >= tail}
        protected = anchors | core
        paid = protected.union(*(context[visit] for visit in protected))
        return dict(core=sorted(core), protected=sorted(protected), paid=sorted(paid))

    blocks = issued // width
    order = span_order(blocks)
    stops = {"third": (blocks + 2) // 3, "half": (blocks + 1) // 2, "full": blocks}
    schedules = {"anchors": stage(set(), issued)}
    for name, stop in stops.items():
        schedules[f"span_{name}"] = stage(set(order[:stop]), blocks * width)
        if name != "full":
            schedules[f"chronological_{name}"] = stage(set(range(stop)), blocks * width)
    return dict(issued=issued, admitted=len(visit_ids), block_width=width, full_blocks=blocks,
                partial_issued=issued % width, block_order=order, anchors=sorted(anchors),
                stages=schedules)


def metadata(document):
    inventories(document)
    clock = StereoBlocks()
    return [
        (visit, row["channel"], row["actual_rf_hz"], row["valid_start_counter"], clock.next(row)[0])
        for visit, (row, _) in visit_pairs(document["source"]["probes"])
    ]


def load(case):
    if case == "DS30-0008":
        request = load_checked(DENSE / "request.json", REQUEST_SHA)
        raw = load_checked(HERE / "measurements/dense-full-short-raw.json.gz", RAW_SHA)
        if (raw["candidate"]["native_sha256"] != request["original"]["native_sha256"]
                or raw["binding"]["archive"]["snapshots_sha256"] != request["archive"]["snapshots_sha256"]):
            raise ValueError("Dense paid acquisition and saved packet have different authority")
        packet, pin, cost = DENSE / "original-detections.json", NATIVE_SHA, raw["candidate"]["recipe"]["receiver_audit"]
        receipt_pins = (REQUEST_SHA, RAW_SHA)
    else:
        request = load_checked(WEAK / "result.json", WEAK_CONTROL_SHA)["inputs"]
        packet, pin = WEAK / "detections.json", request["native"][7:]
        cost = load_checked(WEAK_RAW, WEAK_RAW_SHA)["receiver_audit"]
        receipt_pins = (WEAK_CONTROL_SHA, WEAK_RAW_SHA)
    document = load_checked(packet, pin)
    source = document["source"]
    provenance = document["provenance"]
    if (source["input_manifest_sha256"] != request["inventory"]
            or source["raw_recording_authority_digest"] != request["authority"]
            or source["analysis_manifest_sha256"] != cost["analysis_manifest"]
            or request["inventory"] != cost["input_manifest"] or request["authority"] != cost["recording_authority"]
            or provenance["detector_sha256"] != f"sha256:{RECEIVER_SHA}"
            or cost["detector_pin"] != RECEIVER_SHA or provenance["scope"] != "cancellation"
            or provenance["skipped_fast_score"] or not source["qualified"]
            or source["sample_rate_hz"] != 10_000_000):
        raise ValueError("Expected the same authenticated, unfiltered physical receiver inputs")
    return document, cost, dict(packet_sha256=pin, request_sha256=receipt_pins[0],
                                paid_raw_sha256=receipt_pins[1], authority=request["authority"],
                                inventory=request["inventory"])


def audit_owners(case, document, pin):
    cfg = ORIGINAL[case]
    publication = cfg["publication"]
    receipt = load_checked(publication / "joint-research-receipt.json", cfg["owners_sha256"])
    binding = receipt["receipt"]
    terminal_path = publication / "fast-scan-automatic-work" / binding["run_id"] / "terminal.json"
    terminal = load_checked(terminal_path, binding["terminal_sha256"][7:])
    session = document["source"]["session_id"]
    if (terminal["native_sha256"] != f"sha256:{pin}" or terminal["decision"] != "ok"
            or terminal["session_id"] != session or binding["decision"] != "complete"):
        raise ValueError("The full original owners must bind to this signed unfiltered packet")
    ids = {
        "sha256:" + sha256(f"{session}:{row['receiver_id']}:{row['valid_start_counter']}".encode()).hexdigest():
            (row["visit_index"], row["receiver_id"])
        for row in document["source"]["probes"] if row["candidates"]
    }
    by_arm = {}
    if set(receipt["selected_rows"]) != {"c0", "fitted_c"}:
        raise ValueError("Both independently published calibration arms are required")
    for arm, rows in receipt["selected_rows"].items():
        by_arm[arm] = {ids[row[0]] for row in rows}
        if len(by_arm[arm]) != len(rows):
            raise ValueError("Original owner IDs must match unique measured opportunities")
    return by_arm, dict(owners_sha256=cfg["owners_sha256"], terminal_sha256=binding["terminal_sha256"])


def replay(probes, paid):
    state = carrier_continuation.Continuation()
    return [
        state.select(row if row["visit_index"] in paid else dict(row, candidates=[]))
        for row in probes
    ]


def audit(probes, full_history, stage, owners, *, context):
    protected = set(stage["protected"])
    paid = set(stage["paid"]) if context else protected
    observed = replay(probes, paid)
    members = {(row["visit_index"], row["receiver_id"]) for row, selection in zip(probes, observed, strict=True)
               if selection[1] is not None}
    per_radio = defaultdict(Counter)
    for row, original, selection in zip(probes, full_history, observed, strict=True):
        visit, radio = row["visit_index"], row["receiver_id"]
        unpaid = visit not in paid
        stats = per_radio[radio]
        stats.update(factors=len(row["candidates"]) if not unpaid else 0,
                     history_kept=int(selection[1] is not None),
                     omitted_original_history=int(unpaid and original[1] is not None),
                     paid_later_history_losses=int(not unpaid and original[1] is not None and selection[1] is None),
                     protected_history_decision_diffs=int(visit in protected and original[:2] != selection[:2]),
                     protected_history_vote_diffs=int(visit in protected and original != selection))
        if context and visit in protected and original != selection:
            raise ValueError("The planned closure failed to preserve a protected history decision")
    per_arm = {
        arm: dict(full=len(rows), paid=sum(visit in paid for visit, _ in rows),
                  core_or_anchor=sum(visit in protected for visit, _ in rows),
                  paid_history=len(rows & members))
        for arm, rows in owners.items()
    }
    return dict(per_radio={str(k): dict(v) for k, v in per_radio.items()}, per_arm=per_arm)


def price(cost, anchors, paid, visits):
    calls = cost["native"]["native_calls"]
    ns = cost["native"]["native_cpu_ns"]
    if calls != {"full": 2 * anchors, "short_primary": 2 * (visits - anchors)}:
        raise ValueError("Saved native calls do not reproduce the actual mixed aperture schedule")
    skipped = 2 * (visits - paid)
    acquisition = cost["acquire"]["cpu_ns"]
    gross = skipped * ns["short_primary"] / calls["short_primary"]
    return dict(paid_short_lanes=calls["short_primary"] - skipped, skipped_short_lanes=skipped,
                fallback_retained_short_prefix_bytes=skipped * 120_000 * 4,
                gross_mean_short_credit_cpu_s=gross / 1e9,
                original_short_cpu_s=ns["short_primary"] / 1e9,
                original_full_cpu_s=ns["full"] / 1e9,
                original_other_acquisition_cpu_s=(acquisition - sum(ns.values())) / 1e9,
                original_acquisition_cpu_s=acquisition / 1e9,
                original_acquisition_elapsed_s=cost["acquire"]["wall_ns"] / 1e9)


def write_json(path, body):
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    with path.open("xb") as stream:
        stream.write(payload + b"\n")
    return sha256(payload + b"\n").hexdigest()


def run(output):
    if not output.parent.resolve(strict=True).is_relative_to(Path("/tmp")):
        raise ValueError("Use a fresh trial directory in Gauss tmpfs /tmp")
    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != CONTINUATION_SHA:
        raise ValueError("The released continuation source changed")
    start_cpu, start_wall = process_time(), perf_counter()
    output.mkdir()
    sources = {case: load(case) for case in ORIGINAL}
    ledgers = {case: metadata(doc) for case, (doc, _, _) in sources.items()}
    plans = {case: plan(ledgers[case], doc["provenance"]["window_count"])
             for case, (doc, _, _) in sources.items()}
    plan_pin = write_json(output / "metadata-plan.json", plans)

    result = {}
    for case, (doc, cost, pins) in sources.items():
        source = doc["source"]
        probes = source["probes"]
        if (signature(source, doc["provenance"]["detector_sha256"], probes) != source["analysis_manifest_sha256"]
                or sum(len(row["candidates"]) for row in probes) != cost["selected"]):
            raise ValueError("Saved receiver proposals differ from the original detection commitment")
        owners, proof = audit_owners(case, doc, pins["packet_sha256"])
        enrollment = plans[case]
        visits, anchors = enrollment["admitted"], len(enrollment["anchors"])
        complete = set(enrollment["stages"]["span_full"]["paid"])
        if complete != {row[0] for row in ledgers[case]}:
            raise ValueError("Full coverage failed the source identity check")
        full_history = replay(probes, complete)
        timestamps = {row[0]: row[3] for row in ledgers[case]}
        stages = {}
        for name, stage in enrollment["stages"].items():
            times = sorted(timestamps[visit] for visit in stage["core"])
            stages[name] = dict(core_visits=len(times), protected_visits=len(stage["protected"]),
                                paid_visits=len(stage["paid"]),
                                core_span_s=(times[-1] - times[0]) / 1e7 if times else None,
                                core_max_gap_s=max((b - a for a, b in zip(times, times[1:])), default=0) / 1e7,
                                exact=audit(probes, full_history, stage, owners, context=True),
                                unprotected=audit(probes, full_history, stage, owners, context=False),
                                priced=price(cost, anchors, len(stage["paid"]), visits),
                                unprotected_price=price(cost, anchors, len(stage["protected"]), visits))
        result[case] = dict(inputs=pins | proof, issued=enrollment["issued"], admitted=visits,
                            full_anchor_visits=anchors, original_layout=ORIGINAL[case]["layout"],
                            full_blocks=enrollment["full_blocks"], trailing_slots=enrollment["partial_issued"],
                            stages=stages)
    write_json(output / "audit.json", dict(
        metadata_plan_sha256=plan_pin, continuation_sha256=CONTINUATION_SHA,
        protocol_sha256=sha256((HERE / "span-sweep-schedule-protocol.md").read_bytes()).hexdigest(),
        source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        waveform_reads=0, catalogue_reads=0, numerical_solves=0, results=result,
        ledger_audit_cpu_s=process_time() - start_cpu, ledger_audit_elapsed_s=perf_counter() - start_wall))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output)
