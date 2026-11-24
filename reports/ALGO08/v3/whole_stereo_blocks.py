"""Price a signed whole-stereo short schedule before touching the position solver."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from pathlib import Path
from time import process_time

from leo.contracts.digests import canonical_digest
from tools.pipeline_eval.variants.capture_bursts import inventories, visit_pairs


HERE = Path(__file__).resolve().parent
DENSE = Path("/dev/shm/leo-held-anchor-selected-dense-01")
REQUEST_SHA = "8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502"
NATIVE_SHA = "ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85"
RAW_SHA = "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38"
RECEIVER_SHA = "13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40"
CONTINUATION_SHA = "f13fc2e02be5474de37b3efb5fba195e3a45daf534e3fa4e7d60c76500cef9ee"
GATE_S = 3.49
BLACKOUT_RULE = dict(anchor_period=8, short_period=3, keep_short=[0, 1], scope=["edge", "channel", "actual_rf_hz"],
                     reset="new original recording; no gap reset", excludes="only original admitted opportunities advance",
                     omitted_outputs="empty stereo probe pair at original hardware counters")


def load_checked(path, pin):
    body = path.read_bytes()
    if sha256(body).hexdigest() != pin:
        raise ValueError(f"Unreviewed sealed source {path}")
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)


class StereoBlocks:
    def __init__(self):
        self.streams = {}

    def next(self, metadata):
        stream = tuple(metadata[key] for key in ("edge", "channel", "actual_rf_hz"))
        now = metadata["valid_start_counter"]
        count, seen_short, prior = self.streams.get(stream, (0, 0, None))
        if prior is not None and now <= prior:
            raise ValueError("Detector apertures require original increasing hardware counters")
        anchor = count % 8 == 0
        mode = "full" if anchor else "short_primary"
        keep = anchor or seen_short % 3 != 2
        self.streams[stream] = (count+1, seen_short+int(not anchor), now)
        return mode, keep


def schedule(native):
    inventories(native)
    metadata = StereoBlocks()
    return [(visit, *metadata.next(pair[0])) for visit, pair in visit_pairs(native["source"]["probes"])]


def signature(source, detector, probes):
    return canonical_digest(["cancellation", source["raw_recording_authority_digest"], detector.removeprefix("sha256:"), probes])


def project(native, decisions):
    source, provenance = native["source"], native["provenance"]
    before = source["probes"]
    if (provenance["detector_sha256"] != "sha256:"+RECEIVER_SHA or provenance["scope"] != "cancellation"
            or not source["qualified"] or source["sample_rate_hz"] != 10_000_000
            or provenance["skipped_fast_score"] or signature(source, provenance["detector_sha256"], before) != source["analysis_manifest_sha256"]):
        raise ValueError("Only the genuine unfiltered mixed detector supplies these pre-history rows")
    after, kept, skipped = [], Counter(), Counter()
    for (visit, mode, keep), (observed, pair) in zip(decisions, visit_pairs(before), strict=True):
        if visit != observed or mode not in ("full", "short_primary") or (not keep and mode == "full"):
            raise ValueError("The frozen whole-stereo schedule changed its aperture")
        if keep:
            for row in pair:
                candidates = row["candidates"]
                if (len(candidates) > 1 or any(not f["passed_fractional_margin_gate"] for f in candidates)
                        or (mode == "short_primary" and candidates and candidates[0]["candidate_rank"] != 0)):
                    raise ValueError("Paid measured rows must match the archived proposal ABI")
            after.extend(pair)
            kept[mode] += 2
        else:
            after.extend(dict(row, candidates=[]) for row in pair)
            skipped[mode] += 2
    recipe = dict(kind="saved whole-stereo short-opportunity counterfactual", parent=provenance["detector_sha256"],
                  rule=BLACKOUT_RULE, continuation="unfiltered original within-lane selection")
    detector = canonical_digest(recipe)
    derived = signature(source, detector, after)
    packet = dict(native, source=dict(source, probes=after, analysis_manifest_sha256=derived),
                  provenance=dict(provenance, detector_sha256=detector, run_id="blind-compact-"+derived[7:39]))
    return packet, dict(recipe=recipe, detector_sha256=detector, native_sha256=canonical_digest(packet),
                        kept_native_lanes=dict(kept), skipped_native_lanes=dict(skipped),
                        schedule_sha256=canonical_digest(decisions), skipped_visits=[visit for visit, _, keep in decisions if not keep])


def history(probes):
    from tools.pipeline_eval.variants import carrier_continuation

    if sha256(Path(carrier_continuation.__file__).read_bytes()).hexdigest() != CONTINUATION_SHA:
        raise ValueError("The original released receiver/channel/RF continuation changed")
    state = carrier_continuation.Continuation()
    selected = []
    for row in probes:
        _, keep, _ = state.select(row)
        selected.append([row["candidates"][keep]] if keep is not None else [])
    return selected


def exposure(original, derived, skipped):
    """Only an after-schedule audit may reveal originally measured skipped outcomes."""
    before, after = original["source"]["probes"], derived["source"]["probes"]
    original_history, masked_history = history(before), history(after)
    seen = {}
    for radio in (0, 1):
        counts = Counter()
        for row, masked, full, masked_causal in zip(before, after, original_history, masked_history, strict=True):
            if row["receiver_id"] != radio:
                continue
            absent = row["visit_index"] in skipped
            if (masked_causal and masked_causal != masked["candidates"]) or (absent and masked["candidates"]):
                raise ValueError("An omitted lane lent factor evidence to the masked continuation")
            counts.update(unfiltered_full=len(row["candidates"]), unfiltered_mask=len(masked["candidates"]),
                          history_full=len(full), history_mask=len(masked_causal),
                          history_direct_loss=int(absent and bool(full)),
                          history_paid_later_loss=int(not absent and bool(full) and not masked_causal),
                          history_paid_later_gain=int(not absent and not full and bool(masked_causal)))
        seen[radio] = dict(counts)
    return dict(per_radio=seen, full_history_rows_sha256=canonical_digest(original_history),
                masked_history_rows_sha256=canonical_digest(masked_history), released_history_sha256=CONTINUATION_SHA)


def price(native_cost, audit):
    original = native_cost["native"]["native_calls"]
    charged = native_cost["native"]["native_cpu_ns"]
    if set(original) != {"full", "short_primary"} or any(
        audit["kept_native_lanes"].get(k, 0)+audit["skipped_native_lanes"].get(k, 0) != value for k, value in original.items()
    ):
        raise ValueError("Masked schedule and original audited native calls do not agree")
    removed = audit["skipped_native_lanes"].get("short_primary", 0)
    gross = removed * charged["short_primary"] / original["short_primary"] / 1e9
    acquisition = native_cost["acquire"]["cpu_ns"]/1e9
    return dict(gross_credit_cpu_s=gross, gate_cpu_s=GATE_S, eligible=gross > GATE_S,
                gate_margin_cpu_s=gross-GATE_S, original_acquisition_cpu_s=acquisition,
                modeled_acquisition_cpu_s=acquisition-gross, original_calls=original,
                original_native_cpu_s=sum(charged.values())/1e9,
                original_short_cpu_s=charged["short_primary"]/1e9, non_native_cpu_s=acquisition-sum(charged.values())/1e9,
                skip_rate=removed/original["short_primary"], fixed_authenticated_reads=True)


def plan(root):
    start = process_time()
    if not root.parent.resolve(strict=True).is_relative_to(Path("/dev/shm")):
        raise ValueError("Use a fresh tmpfs trial directory")
    request = load_checked(DENSE/"request.json", REQUEST_SHA)
    original = load_checked(DENSE/"original-detections.json", NATIVE_SHA)
    decisions = schedule(original)
    packet, proof = project(original, decisions)
    clock = process_time()-start
    raw = load_checked(HERE/"measurements/dense-full-short-raw.json.gz", RAW_SHA)
    native_cost = raw["candidate"]["recipe"]["receiver_audit"]
    if (request["original"]["native_sha256"] != "sha256:"+NATIVE_SHA or raw["candidate"]["native_sha256"] != "sha256:"+NATIVE_SHA
            or native_cost["analysis_manifest"] != original["source"]["analysis_manifest_sha256"]
            or native_cost["recording_authority"] != request["authority"] or request["archive"]["snapshots_sha256"] != raw["binding"]["archive"]["snapshots_sha256"]):
        raise ValueError("The current dense native and acquisition budget do not share original identity")
    from leo.contracts.digests import canonical_json_bytes

    root.mkdir()
    (root/"candidate-detections.json").write_bytes(canonical_json_bytes(packet))
    clocks = price(native_cost, proof)
    with (root/"plan.json").open("x") as stream:
        json.dump(dict(frozen_plan=proof, budget=clocks, planning_including_source_cpu_s=clock,
                       source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(), request_sha256=REQUEST_SHA,
                       raw_receipt_sha256=RAW_SHA, original_native_sha256=NATIVE_SHA,
                       protocol_sha256=sha256((HERE/"whole-stereo-blocks-protocol.md").read_bytes()).hexdigest()),
                  stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    diagnostic = exposure(original, packet, set(proof["skipped_visits"]))
    with (root/"history-audit.json").open("x") as stream:
        json.dump(diagnostic, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    plan(parser.parse_args().output)
