"""Frozen fixed-owner alias arithmetic with a bounded peer continuity check."""

import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import mean

from first_member_0163_owner_join import PAIR, PAIR_PIN
from prefix_transfer_0419 import ARMS, checked, lane_key, metadata, observation_id
from verified_window_transfer_0163 import PINS, controls


TARGET = (61, 0)
CFO = "fractional_tracking_cfo_hz"
EPOCH = "integer_epoch_sample"
FRACTION = "fractional_epoch_offset_samples"
RATE = 10_000_000
PERIOD = 1 / 4.4e-6
SOURCE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/src/leo/analysis")
RELEASE_PINS = {"research/retained_track_likelihood.py": "73c24d054d5676c7d7051779a6960f8f692ce0d97bc23d292470aa01f6110bcf",
                "localization_v3/marginal.py": "c80ac51249578e8a2c6c6a13a04aaa22a168353b2c758155858106b91507b609"}


def alias_at(cfo, prediction):
    residual = cfo - prediction
    integer = round(-residual / PERIOD)
    return dict(ordinary_residual_hz=residual, nearest_integer=integer, nearest_alias_residual_hz=residual + integer * PERIOD)


def affine_value(points, time):
    x, y = zip(*points, strict=True)
    center, intercept = mean(x), mean(y)
    slope = sum((a - center) * (b - intercept) for a, b in points) / sum((a - center)**2 for a in x)
    return intercept + slope * (time - center)


def nearby(lanes, target, owner, roster, session):
    fields = ("receiver_id", "edge", "channel", "actual_rf_hz")
    peers = [r for r in lanes.values() if lane_key(r) != TARGET and len(r["candidates"]) == 1
             and all(r[k] == target[k] for k in fields) and roster.get(observation_id(session, r)) == owner]
    counter = target["valid_start_counter"]
    before = sorted((r for r in peers if r["valid_start_counter"] < counter), key=lambda r: r["valid_start_counter"])[-2:]
    after = sorted((r for r in peers if r["valid_start_counter"] > counter), key=lambda r: r["valid_start_counter"])[:2]
    return before + after if len(before) == len(after) == 2 else []


def continuity(peers, counter, original, sparse, session):
    rows, points = [], []
    for p in peers:
        t = (p["valid_start_counter"] - counter) / RATE
        cfo = p["candidates"][0][CFO]
        lift = 0 if not points else alias_at(cfo, points[-1][1])["nearest_integer"]
        points.append((t, cfo + lift * PERIOD))
        rows.append(dict(visit=p["visit_index"], original_observation_id=observation_id(session, p),
                         absolute_start_counter=p["valid_start_counter"], time_from_target_s=t,
                         signed_cfo_hz=cfo, alias=lift))
    prediction = affine_value(points, 0.0)
    leave_one_out = [affine_value(points[:i] + points[i+1:], 0.0) for i in range(len(points))]
    alternatives = [alias_at(sparse, x) for x in leave_one_out]
    residuals = [row["nearest_alias_residual_hz"] for row in alternatives]
    return dict(peers=rows, peer_prediction_hz=prediction, leave_one_peer_out_prediction_range_hz=[min(leave_one_out), max(leave_one_out)],
                installed=alias_at(original, prediction), sparse=alias_at(sparse, prediction),
                nearest_alias_values_under_leave_one_out=sorted({row["nearest_integer"] for row in alternatives}),
                sparse_nearest_residual_range_hz=[min(residuals), max(residuals)])


def summarize():
    for name, pin in RELEASE_PINS.items():
        if sha256((SOURCE / name).read_bytes()).hexdigest() != pin:
            raise ValueError("The installed native period or residual model differs")
    _, full, _, lanes, _, owners, _ = controls()
    docs = json.loads(gzip.decompress(checked(PAIR, PAIR_PIN)))["documents"]
    packets = [docs[f"{mode}/detections.json"]["document"] for mode in ("named", "integrated")]
    original, sparse = [next(r for r in packet["source"]["probes"] if lane_key(r) == TARGET) for packet in packets]
    if metadata(original) != metadata(sparse) or lanes[TARGET] != original or original["channel"] != 6:
        raise ValueError("First verify the complete original opportunity and full-archive provenance")
    a, = original["candidates"]
    b, = sparse["candidates"]
    session = full["source"]["session_id"]
    id_ = observation_id(session, original)
    arms = {}
    for arm in ARMS:
        roster = owners["installed"][arm]
        owner = roster[id_]
        peers = nearby(lanes, original, owner, roster, session)
        arms[arm] = dict(owner=owner, exact_saved_prediction_hz=None, exact_saved_residual_hz=None,
                         missing_exact_reason="Typed per-point residuals were not persisted with original publication",
                         local_peer_continuity=continuity(peers, original["valid_start_counter"], a[CFO], b[CFO], session)
                         if peers else None)
    counter = original["valid_start_counter"]
    return dict(case="DS30-0163", original_publication_sha256=PINS["installed/candidate/joint-research-receipt.json"],
                original_receiver_packets_sha256=PAIR_PIN, source=metadata(original), observation_id=id_,
                sample_rate_hz=RATE, alias_period_hz=PERIOD, period_basis="released signed v3 retained_track_likelihood",
                installed_alias_and_residual_source_sha256=RELEASE_PINS,
                residual_definition="signed measured CFO + integer times native alias period - fixed prediction",
                atoms=dict(installed=a | {"absolute_integer_epoch": counter + a[EPOCH]},
                           sparse=b | {"absolute_integer_epoch": counter + b[EPOCH]}),
                sparse_minus_installed_fractional_epoch_samples=(b[EPOCH] - a[EPOCH]) + (b[FRACTION] - a[FRACTION]),
                sparse_relative_to_original=alias_at(b[CFO], a[CFO]), arms=arms,
                evidence="local fixed-owner peer continuity only, no new fit or assignment")


if __name__ == "__main__":
    print(json.dumps(summarize(), sort_keys=True, indent=2, allow_nan=False))
