"""Vectorized equivalent of the frozen per-track blind training objective."""

from dataclasses import dataclass

import numpy as np


@dataclass
class PackedScan:
    position: np.ndarray
    velocity: np.ndarray
    measured: np.ndarray
    starts: np.ndarray
    training_indices: np.ndarray
    training_starts: np.ndarray
    training_counts: np.ndarray
    training_groups: np.ndarray
    weights: np.ndarray


def pack(prepared):
    if not prepared:
        raise ValueError("empty track support")
    counts = np.asarray([len(t["measured_hz"]) for t in prepared])
    starts = np.r_[0, np.cumsum(counts)[:-1]]
    masks = [np.asarray(t["training_mask"], dtype=bool) for t in prepared]
    training_counts = np.asarray([np.sum(m) for m in masks])
    if np.any(training_counts == 0):
        raise ValueError("each track requires training rows")
    return PackedScan(
        np.concatenate([t["position"] for t in prepared], axis=1),
        np.concatenate([t["velocity"] for t in prepared], axis=1),
        np.concatenate([t["measured_hz"] for t in prepared]),
        starts,
        np.flatnonzero(np.concatenate(masks)),
        np.r_[0, np.cumsum(training_counts)[:-1]],
        training_counts,
        np.repeat(np.arange(len(prepared)), training_counts),
        np.asarray([t["weight_s"] for t in prepared], dtype=float),
    )


def score(packed, receiver, up, block_size=128):
    """Return objective, candidate row indices, and train-only offsets/RMS.

    Visibility, weights and the 800 Hz cap reproduce the existing frozen model.
    Reserved frequencies are not indexed. Candidate blocks retain original order,
    including its deterministic first-winner tie break.
    """
    if block_size < 1:
        raise ValueError("positive candidate block size required")
    count = len(packed.weights)
    best = np.full(count, np.inf)
    offsets = np.full(count, np.nan)
    winners = np.full(count, -1, dtype=int)
    columns = np.arange(count)
    for start in range(0, len(packed.position), block_size):
        delta = packed.position[start : start + block_size] - receiver
        velocity = packed.velocity[start : start + block_size]
        distance = np.sqrt(np.sum(delta**2, axis=-1))
        prediction = -11.2e9 / 299792.458 * np.sum(delta * velocity, axis=-1) / distance
        visibility = np.maximum.reduceat(np.sum(delta * up, axis=-1), packed.starts, axis=1) >= 0
        residual = packed.measured[packed.training_indices] - prediction[:, packed.training_indices]
        means = np.add.reduceat(residual, packed.training_starts, axis=1) / packed.training_counts
        centered = residual - means[:, packed.training_groups]
        rms = np.sqrt(
            np.add.reduceat(centered**2, packed.training_starts, axis=1) / packed.training_counts
        )
        rms[~visibility] = np.inf
        indices = np.argmin(rms, axis=0)
        values = rms[indices, columns]
        improved = values < best
        best[improved] = values[improved]
        offsets[improved] = means[indices, columns][improved]
        winners[improved] = start + indices[improved]
    objective = np.sqrt(
        np.sum(packed.weights * np.minimum(best, 800.0) ** 2) / np.sum(packed.weights)
    )
    return float(objective), winners, offsets, best
