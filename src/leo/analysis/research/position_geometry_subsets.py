"""Truth-blind sparse design from causal orbit-state geometry.

The response frequency is deliberately not an input.  Candidate packets are
scored with receiver-position Doppler Jacobians at a fixed external grid after
projecting out a per-track offset and orbit phase-rate direction.  A greedy
D-optimal traversal then favours complementary horizontal directions.
"""
from __future__ import annotations

import hashlib
import itertools

import numpy as np

from leo.analysis.research.formal_orbit import doppler_hz, phase_rate_design_hz_per_s_h


def _jacobian(receiver, p, v, step_km=1.0):
    up = np.asarray(receiver, float) / np.linalg.norm(receiver)
    east = np.cross(np.asarray([0.0, 0.0, 1.0]), up)
    if np.linalg.norm(east) < 1e-8:
        east = np.cross(np.asarray([0.0, 1.0, 0.0]), up)
    east /= np.linalg.norm(east)
    north = np.cross(up, east)
    axes = np.asarray((east, north)) * step_km
    return np.column_stack([
        (doppler_hz(receiver + axis, p, v) - doppler_hz(receiver - axis, p, v))
        / (2 * step_km)
        for axis in axes
    ])


def _projected_information(jacobian, nuisance):
    q = np.linalg.pinv(nuisance, rcond=1e-10) @ jacobian
    residual = jacobian - nuisance @ q
    return residual.T @ residual


def geometry_packet_order(
    observation_ids,
    training,
    track,
    time_s,
    age_h,
    p_km,
    v_km_s,
    phase_p_minus_km,
    phase_v_minus_km_s,
    phase_p_plus_km,
    phase_v_plus_km_s,
    receiver_grid_ecef_km,
    *,
    seed=0,
    packet_size=3,
    candidate_limit=12,
    max_count=None,
):
    """Return a nested order using no measured frequencies or fitted values.

    Each track contributes packets in rounds.  Its next packet is selected from
    at most ``candidate_limit`` evenly spaced remaining rows, which bounds the
    exhaustive combination search without privileging a particular campaign.
    Packet information is normalized at each external receiver-grid point, then
    greedily merged by log determinant.  The hash seed only resolves numerical
    ties.
    """
    ids = np.asarray(observation_ids)
    fit = np.asarray(training, bool)
    labels = np.asarray(track)
    times = np.asarray(time_s, float)
    grid = np.asarray(receiver_grid_ecef_km, float)
    n = len(ids)
    arrays = (fit, labels, times, age_h, p_km, v_km_s, phase_p_minus_km,
              phase_v_minus_km_s, phase_p_plus_km, phase_v_plus_km_s)
    if any(len(x) != n for x in arrays) or grid.ndim != 2 or grid.shape[1] != 3:
        raise ValueError("incompatible geometry arrays")
    if len(np.unique(ids)) != n:
        raise ValueError("duplicate observation IDs")
    if packet_size < 3 or candidate_limit < packet_size:
        raise ValueError("packet_size >= 3 and candidate_limit >= packet_size required")
    if max_count is not None and max_count < 1:
        raise ValueError("max_count must be positive")

    # Precompute local linear designs; scaling makes grid points contribute
    # equally even when their absolute sensitivity differs.
    jac = []
    phase = []
    for receiver in grid:
        j = _jacobian(receiver, np.asarray(p_km), np.asarray(v_km_s))
        d = phase_rate_design_hz_per_s_h(
            receiver, phase_p_minus_km, phase_v_minus_km_s,
            phase_p_plus_km, phase_v_plus_km_s, age_h)
        scale = np.sqrt(np.mean(np.sum(j[fit] ** 2, axis=1)))
        jac.append(j / max(scale, 1e-12))
        phase.append(np.asarray(d) / max(scale, 1e-12))

    remaining = {}
    for label in np.unique(labels[fit]):
        rows = np.flatnonzero(fit & (labels == label))
        remaining[label.item() if hasattr(label, "item") else label] = list(
            rows[np.lexsort((ids[rows].astype(str), times[rows]))]
        )
    output = []
    total_info = np.eye(2) * 1e-6
    while any(remaining.values()) and (max_count is None or len(output) < max_count):
        packets = []
        for label, rows in remaining.items():
            if not rows:
                continue
            take = min(packet_size, len(rows))
            if take < 3:
                # Residual information is zero after two nuisance directions;
                # retain leftovers only after informative complete packets.
                info = np.zeros((2, 2))
                choice = tuple(rows)
            else:
                positions = np.unique(
                    np.rint(
                        np.linspace(0, len(rows) - 1, min(candidate_limit, len(rows)))
                    ).astype(int)
                )
                candidates = [rows[x] for x in positions]
                best = None
                for choice0 in itertools.combinations(candidates, take):
                    info0 = np.zeros((2, 2))
                    for j, d in zip(jac, phase, strict=True):
                        rr = np.asarray(choice0)
                        nuisance = np.column_stack((np.ones(take), d[rr]))
                        info0 += _projected_information(j[rr], nuisance) / len(grid)
                    score0 = float(np.trace(info0))
                    tie = hashlib.sha256(
                        f"geometry-packet-v1\0{seed}\0".encode()
                        + "\0".join(map(str, ids[list(choice0)])).encode()).digest()
                    key = (score0, tie)
                    if best is None or key > best[0]:
                        best = (key, tuple(choice0), info0)
                _, choice, info = best
            tie = hashlib.sha256(f"geometry-track-v1\0{seed}\0{label}".encode()).digest()
            packets.append((tie, label, choice, info))
        # Packet geometry is fixed during the round.  Recompute only its cheap
        # 2x2 marginal gain as the aggregate information changes.
        while packets and (max_count is None or len(output) < max_count):
            base_logdet = np.linalg.slogdet(total_info)[1]
            index = max(range(len(packets)), key=lambda i: (
                np.linalg.slogdet(total_info + packets[i][3])[1] - base_logdet,
                packets[i][0]))
            tie, label, choice, info = packets.pop(index)
            allowed = len(choice) if max_count is None else min(
                len(choice), max_count-len(output))
            output.extend(ids[list(choice)[:allowed]].tolist())
            total_info += info
            chosen = set(choice)
            remaining[label] = [x for x in remaining[label] if x not in chosen]
    return tuple(str(x) for x in output)
