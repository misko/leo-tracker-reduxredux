"""Join exact receiver/RF observations without held outcome features."""

import hashlib
import math
from collections import defaultdict

SEED = 2026092711


def training(session, visit):
    return int(hashlib.sha256(f"{SEED}:visit:{session}:{visit}".encode()).hexdigest()[:8], 16) % 10 < 6


def build(session, probes, tracks):
    lanes = defaultdict(list)
    visits = defaultdict(list)
    for p in probes:
        key = p["receiver"], p["rf_hz"]
        visits[*key, p["visit_index"]].append(p)
        if training(session, p["visit_index"]):
            lanes[key].append(p)
    rows = []
    for t in tracks:
        key = t["receiver_id"], t["rf_hz"]
        for v, m in zip(t["visits"], t["training_mask"], strict=True):
            if training(session, v) != m:
                raise ValueError("stored training partition differs")
            if not any(p["passing"] > 0 for p in visits[*key, v]):
                raise ValueError("track visit lacks matching passing probe")
        ps = lanes[key]
        if not ps:
            raise ValueError("no training opportunity")
        empty = sum(p["passing"] == 0 for p in ps)
        n = len(ps)
        p = (empty + 0.5) / (n + 1)
        rows.append(dict(track_id=t["track_id"], receiver_id=key[0], rf_hz=key[1],
                         training_probes=n, training_empty=empty,
                         empty_fraction_smoothed=p, empty_logit=math.log(p/(1-p))))
    return rows
