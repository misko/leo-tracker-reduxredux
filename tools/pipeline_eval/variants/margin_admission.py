"""Calibrate and apply one removal-only native fractional-margin threshold."""

import math
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256

STOCK = 0.025
THIN_SALT = "same-positive-budget-20261119:"
FLAG = "passed_fractional_margin_gate"


def probe_margin(probe):
    return max(
        (c["fractional_margin"] for c in probe["candidates"] if c[FLAG]),
        default=-math.inf,
    )


def threshold(recordings):
    """Each input is a list of (wide maximum, capture-era positive) probe pairs."""
    if not recordings or any(not group for group in recordings):
        raise ValueError("each calibration recording needs valid receiver probes")
    positive, teacher = Fraction(), Fraction()
    loss = defaultdict(Fraction)
    for group in recordings:
        scale = Fraction(1, len(group) * len(recordings))
        teacher += scale * sum(bool(label) for _, label in group)
        for score, _ in group:
            if score >= STOCK:
                if not math.isfinite(score):
                    raise ValueError("admitted margins must be finite")
                loss[score] += scale
                positive += scale
    retained = positive
    winner, gap = STOCK, abs(positive - teacher)
    for score, removed in sorted(loss.items()):
        retained -= removed
        error = abs(retained - teacher)
        if error < gap:
            winner, gap = math.nextafter(score, math.inf), error
    return winner


def bind(probes, minimum):
    """Flip admitted flags only. Scores, rank and observations are unchanged."""
    if not math.isfinite(minimum) or minimum < STOCK:
        raise ValueError("finite removal-only margin required")
    for probe in probes:
        for c in probe["candidates"]:
            margin = c["fractional_margin"]
            if not math.isfinite(margin) or c[FLAG] is not (margin >= STOCK):
                raise ValueError("source candidate differs from its ordinary gate")
            c[FLAG] = margin >= minimum


def thin(probes, keep, session):
    """Uniform deterministic control with the same positive-candidate count."""
    ranked = []
    for p in probes:
        for c in p["candidates"]:
            if c[FLAG]:
                key = (
                    p["visit_index"],
                    p["receiver_id"],
                    p["probe_index"],
                    c["candidate_rank"],
                )
                receipt = sha256((THIN_SALT + session + "/" + "/".join(map(str, key))).encode())
                ranked.append((receipt.digest(), key, c))
    if not 0 <= keep <= len(ranked):
        raise ValueError("invalid positive-candidate budget")
    for rank, (_, _, c) in enumerate(sorted(ranked)):
        c[FLAG] = rank < keep
