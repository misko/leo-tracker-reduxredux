"""Choose two full-data centre fits from a cheap causal calibration scout."""

from contextlib import contextmanager
from hashlib import sha256
from inspect import getsource
from itertools import islice
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch

import numpy as np


DISCOVERY_SHA256 = "7ca045c3809c8da7b57268b9d9bcc4b8a49366e88376250d0b11227ce6d7e26a"
SCOUTS = 6
ROBUST_CAP = 900.0**2


def now():
    return process_time_ns(), perf_counter_ns()


def elapsed(start):
    end = now()
    return dict(cpu_ns=end[0]-start[0], elapsed_ns=end[1]-start[1])


def radio_weights(stats):
    components = len(stats["count"])
    if not np.array_equal(stats["starts"], np.arange(components)):
        return None
    groups = stats["g"]
    if groups.shape != (components,) or np.any((groups < 0) | (groups > 3)):
        return None
    weight = np.minimum(stats["count"], 50) * stats["active"]
    radio = np.stack([weight * (groups < 2), weight * (groups >= 2)])
    if np.any(radio.sum(axis=1) == 0):
        return None
    return radio / radio.sum(axis=1, keepdims=True)


def receiver_scores(cost, weights):
    if cost.ndim != 2 or not cost.shape[1] or cost.shape[0] != weights.shape[1] or np.isnan(cost).any():
        return None
    best = np.maximum(0., np.minimum(ROBUST_CAP, np.min(cost, axis=1)))
    return weights @ best


def scout(stats, offer_stats, initial, sigma, bounds, discovery, audit):
    started = now()
    rows, seen = [], set()
    weights = radio_weights(stats)
    selected = None
    if weights is not None:
        proposals = discovery.seed_calibrations(offer_stats, initial, SCOUTS, seed_policy="anchor-round-robin-v1")
        for index, beta in enumerate(islice(proposals, 1, SCOUTS + 1)):
            state = dict(beta=beta, phases=[], extra={}, smooth=[])
            beta = discovery.project_radio_state(state)["beta"]
            if not np.isfinite(beta).all() or not beta.any() or tuple(beta) in seen:
                continue
            seen.add(tuple(beta))
            _, cost = discovery.proposal_phases(stats, beta, sigma, bounds, return_components=True)
            radio = receiver_scores(cost, weights)
            if radio is not None:
                rows.append((float(max(radio)), float(radio.mean()), index, beta, radio))
        if rows:
            selected = min(rows, key=lambda row: row[:3])
    audit.update(scout=elapsed(started), original_curved=int(np.count_nonzero(stats["active"])),
                 catalogue_rows=len(sigma), requested=[
                    dict(index=row[2], calibration_hz=list(map(float, row[3])), per_radio=list(map(float, row[4])))
                    for row in rows],
                 picked=None if selected is None else selected[2])
    if selected is None:
        return None
    return [initial.copy(), selected[3].copy()]


@contextmanager
def two_seeds(audit):
    from leo.analysis.localization_v3 import discovery

    ordinary = discovery.fresh_discovery
    path = Path(ordinary.__code__.co_filename)
    source = getsource(ordinary)
    start = "    calibrations = ("
    end = "    candidates = []"
    if (sha256(path.read_bytes()).hexdigest() != DISCOVERY_SHA256
            or source.count(start) != 1 or source.count(end) != 1):
        audit["fallback"] = "unsupported_discovery_source"
        yield
        return
    fallback = source[source.index(start):source.index(end)]
    modified = source[:source.index(start)] + (
        "    proposals = _choose(stats, proposals_stats, initial, scan.sigma, bounds)\n"
        "    if proposals is None:\n"
        + "".join(f"    {line}\n" for line in fallback.splitlines())
    ) + source[source.index(end):]
    code = compile(modified, str(path), "exec")

    def run(scan, sigma, *, budget=8, seed_policy="legacy"):
        if (budget, seed_policy) != (4, "legacy"):
            audit["fallback"] = "unsupported_discovery_request"
            return ordinary(scan, sigma, budget=budget, seed_policy=seed_policy)

        def nominate(stats, proposal, initial, width, bounds):
            return scout(stats, proposal, initial, width, bounds, discovery, audit)

        # Look up the currently scoped exact geometry and statistics after
        # entering the ordinary rank wrappers.
        scope = dict(ordinary.__globals__, _choose=nominate)
        exec(code, scope)
        centres = scope["fresh_discovery"](scan, sigma, budget=budget, seed_policy=seed_policy)
        audit["paid_centres"] = len(centres)
        if len(centres) != 2 or audit["picked"] is None:
            audit["fallback"] = "no_supported_scout"
        return centres

    with patch.object(discovery, "fresh_discovery", run):
        yield
