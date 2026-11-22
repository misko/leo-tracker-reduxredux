"""Replay a small chronological raw prefix and trace changed continuation votes."""

import argparse
from collections import defaultdict, deque
from contextlib import ExitStack
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastSegmentSource
from residual_native_trial import ScheduledReceiver, candidates
from selected_changes import bound_native
from tools.algo08_scan import PINS
from tools.pipeline_eval.qualification.full_v5_check import _probe
from tools.pipeline_eval.variants.carrier_continuation import Continuation, votes
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer
from tools.pipeline_eval.variants.experimental.residual_schedule import Replay


def counterfactual(row, history):
    lane = row["receiver_id"], row["channel"], row["actual_rf_hz"]
    receiver = Continuation()
    receiver.by_lane[lane].extend(history)
    _, selected, _ = receiver.select(row)
    return row["candidates"][selected]["candidate_rank"] if selected is not None else None


def explain(row, full_history, partial_history, donor_visits):
    now = row["valid_start_counter"]
    donors = []
    for i, ((t, full), (other, partial), visit) in enumerate(
        zip(full_history, partial_history, donor_visits, strict=True)
    ):
        if t != other:
            raise ValueError("Mismatch in chronological donor slots")
        if full != partial:
            repaired = list(partial_history)
            repaired[i] = (t, full)
            donors.append(dict(visit=visit, age_s=(now-t)/1e7, full_hz=full, conditional_hz=partial,
                               selected_rank_after_restoring_slot=counterfactual(row, repaired)))
    return dict(differing_donors=donors, current_factors=[
        dict(rank=f["candidate_rank"], hz=f["fractional_tracking_cfo_hz"],
             full_votes=votes(f["fractional_tracking_cfo_hz"], full_history, now),
             conditional_votes=votes(f["fractional_tracking_cfo_hz"], partial_history, now))
        for f in row["candidates"]], selected_rank_on_full_history=counterfactual(row, full_history),
        selected_rank_on_conditional_history=counterfactual(row, partial_history))


def trace(pair_path, assets, visits):
    pair = json.loads(pair_path.read_bytes())
    spec = pair["candidate_specification"]
    if spec["schedule"] != "conditional-residual" or not 1 <= visits <= 128:
        raise ValueError("Expected a frozen conditional pair and at most 128 visits")
    runs = pair["runs"]
    documents = {arm: bound_native(pair_path.parent/arm, run) for arm, run in runs.items()}
    expected = {arm: {(r["visit_index"], r["receiver_id"]): r for r in doc["source"]["probes"]
                      if r["visit_index"] < visits} for arm, doc in documents.items()}
    if expected["baseline"].keys() != expected["candidate"].keys():
        raise ValueError("Different admitted opportunities")
    root = pair_path.parent/"candidate"
    session = runs["candidate"]["receipt"]["session_id"]
    native = documents["candidate"]
    inventory = json.loads((root/"fast-scan-inputs"/(session+".json")).read_bytes())
    if canonical_digest(inventory) != native["source"]["input_manifest_sha256"]:
        raise ValueError("Raw inventory differs from the paired result")
    source = FastSegmentSource(inventory["segments"][0], stop_sequence=visits)
    if tuple(source.receiver_ids) != (0, 1) or source.reader.manifest.sample_rate_hz != 10_000_000:
        raise ValueError("Expected native-rate stereo recording")
    edge, = {r["edge"] for r in expected["baseline"].values()}
    asset = assets/(edge+".f32")
    reference = assets/"cancellation-factors.so"
    scheduled = Path(spec["detector"])
    def raw_digest(path):
        return sha256(path.read_bytes()).hexdigest()

    before = documents["baseline"]
    if (raw_digest(asset) != PINS[asset.name] or raw_digest(scheduled) != spec["detector_sha256"]
            or native["source"]["input_manifest_sha256"] != before["source"]["input_manifest_sha256"]
            or native["provenance"]["detector_sha256"] != "sha256:"+spec["detector_sha256"]
            or "sha256:"+raw_digest(reference) != before["provenance"]["detector_sha256"]):
        raise ValueError("Receiver or pilot asset differs from the saved pair")
    pilot = np.fromfile(asset, dtype="<f4")
    modes = ("always-two", "conditional")
    policies = [Replay(mode) for mode in modes]
    indices = defaultdict(lambda: deque(maxlen=12))
    checked, changes = set(), []
    exclusions = {r["visit"]: r["iq_sha256"] for r in native["provenance"]["excluded_windows"]}
    policy_settings = FastScanPolicyV2()
    count = 0
    with ExitStack() as stack:
        receivers = [Receiver(reference, pilot), ScheduledReceiver(scheduled, pilot)]
        for radio in receivers:
            stack.callback(radio.close)
        stack.enter_context(compressed_input_buffer())
        for count, window in enumerate(source.windows(), 1):
            acq, target = window.acquisition, window.target
            index = acq["global_visit"]
            if index != count-1:
                raise ValueError("Expected ordered stereo windows from the start")
            if not valid_window_support(acq, window.sample_rate_hz, window.samples.shape,
                                        (0, 1), policy_settings):
                if exclusions.get(index) != window.iq_sha256:
                    raise ValueError("Unexpected excluded window")
                continue
            center = target["rf_center_hz"]-target["lnb_lo_hz"]-acq["actual_if_center_hz"]
            samples = np.ascontiguousarray(window.samples)
            if (samples.shape != (200000, 2, 2) or samples.dtype != np.dtype("<i2")
                    or target["edge"] != edge or not -4_200_000 <= center <= 4_200_000):
                raise ValueError("Unexpected native stereo layout")
            for lane in (0, 1):
                row = _probe(window, lane, [])
                key = lane, row["channel"], row["actual_rf_hz"]
                histories = [list(p.continuation.by_lane[key]) for p in policies]
                results = []
                for arm, policy, radio in zip(("baseline", "candidate"), policies, receivers, strict=True):
                    def measure(full):
                        operation = radio.timed if full else radio.timed_primary
                        factors, _, _ = operation(samples, lane, center)
                        return candidates(factors)
                    full, seen, chosen = policy.visit(row, measure)
                    if dict(row, candidates=chosen) != expected[arm][index, lane]:
                        raise ValueError(f"Raw replay disagrees with saved {arm} selection at {(index, lane)}")
                    results.append((full, seen, chosen))
                checked.add((index, lane))
                if results[0][2] != results[1][2]:
                    changes.append(dict(visit=index, receiver=lane, channel=row["channel"],
                        conditional_full_scan=results[1][0], same_current_factors=results[0][1]==results[1][1],
                        deployed_ranks=[f["candidate_rank"] for f in results[0][2]],
                        conditional_ranks=[f["candidate_rank"] for f in results[1][2]],
                        **explain(dict(row, candidates=results[1][1]), *histories, indices[key])))
                indices[key].append(index)
    if count != visits or checked != expected["baseline"].keys():
        raise ValueError("Incomplete paired raw prefix")
    return dict(pair_sha256=raw_digest(pair_path), raw_authority=runs["candidate"]["raw_authority"],
                visits=visits, admitted_lanes=len(checked), detector_sha256=[raw_digest(reference), raw_digest(scheduled)],
                selection_changes=changes)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("pair", type=Path)
    cli.add_argument("assets", type=Path)
    cli.add_argument("visits", type=int)
    args = cli.parse_args()
    print(json.dumps(trace(args.pair, args.assets, args.visits), indent=2, allow_nan=False))
