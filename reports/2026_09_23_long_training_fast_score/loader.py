"""Avoid repeated NPZ decompression while preserving frozen session semantics."""

import json

import numpy as np


def load_session(single, directory, expected_session):
    receipt_path = directory / "cache_receipt.json"
    cache_path = directory / "state_cache.npz"
    receipt = json.loads(receipt_path.read_text())
    if receipt["session_id"] != expected_session:
        raise ValueError("cache session differs from frozen TRAIN order")
    with np.load(cache_path, allow_pickle=False) as archive:
        position = archive["position_ecef_km"]
        velocity = archive["velocity_ecef_km_s"]
        grid = archive["receive_plus_tau_offset_ns"]
        candidate_ids = archive["candidate_id"]
    prepared = []
    for track in receipt["prepared_evidence"]["tracks"]:
        times = np.asarray(track["times_s"], dtype=float)
        if np.ptp(times) < 3.0:
            continue
        pos, vel = single.interpolate_track(position, velocity, grid, times)
        prepared.append({
            "track_id": track["track_id"], "times_s": times,
            "measured_hz": np.asarray(track["measured_hz"]),
            "training_mask": np.asarray(track["training_mask"], dtype=bool),
            "weight_s": int(len(np.unique(np.floor(times)))),
            "position": pos, "velocity": vel,
        })
    return {"session_id": expected_session, "prepared": prepared,
            "candidate_ids": candidate_ids,
            "weight": sum(track["weight_s"] for track in prepared),
            "receipt": receipt_path, "cache": cache_path}
