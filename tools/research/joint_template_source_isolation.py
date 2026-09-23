"""Frozen numerical core for the bounded two-template source-isolation replay.

This module performs no recording access.  A later sealed runner may supply six
20 ms IQ windows and templates bound by the reviewed metadata artifact.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class JointTemplateFit:
    residual_cfo_hz: tuple[float, ...]
    amplitudes: tuple[complex, ...]
    train_sse: float
    held_sse: float
    held_sample_count: int
    gram_condition: float
    held_gram_condition: float
    train_rank: int
    held_rank: int


def seeded_group_split(group_ids: np.ndarray, *, seed: int = 20260925) -> np.ndarray:
    """Return a deterministic 50% train mask over whole physical groups."""

    group_ids = np.asarray(group_ids)
    groups = np.unique(group_ids)
    if groups.size < 2:
        raise ValueError("at least two physical groups are required")
    rng = np.random.default_rng(seed)
    train = set(rng.permutation(groups)[: groups.size // 2].tolist())
    return np.asarray([group in train for group in group_ids], dtype=bool)


def _design(
    templates: np.ndarray,
    sample_indices: np.ndarray,
    frequencies_hz: np.ndarray,
    sample_rate_hz: float,
) -> np.ndarray:
    phase = np.exp(2j * np.pi * frequencies_hz[:, None] * sample_indices[None, :] / sample_rate_hz)
    expanded_phase = np.repeat(phase, templates.shape[1], axis=0)
    return (templates.reshape(-1, templates.shape[-1]) * expanded_phase).T


def _solve(design: np.ndarray, response: np.ndarray) -> tuple[np.ndarray, float, float]:
    amplitudes, _, _, _ = np.linalg.lstsq(design, response, rcond=None)
    residual = response - design @ amplitudes
    return amplitudes, float(np.vdot(residual, residual).real), 0.0


def fit_templates(
    response: np.ndarray,
    templates: np.ndarray,
    sample_indices: np.ndarray,
    train_mask: np.ndarray,
    *,
    sample_rate_hz: float,
    frequency_grid_hz: np.ndarray | None = None,
) -> JointTemplateFit:
    """Fit template CFO residuals and amplitudes on train samples, then score held samples."""

    response = np.asarray(response, dtype=np.complex128)
    templates = np.asarray(templates, dtype=np.complex128)
    sample_indices = np.asarray(sample_indices, dtype=float)
    train_mask = np.asarray(train_mask, dtype=bool)
    if templates.ndim != 3 or templates.shape[2] != response.size:
        raise ValueError("templates must have shape (source, tone, sample)")
    if sample_indices.shape != response.shape or train_mask.shape != response.shape:
        raise ValueError("sample indices and split must match response")
    if not train_mask.any() or train_mask.all():
        raise ValueError("both train and held samples are required")
    grid = (
        np.arange(-2500.0, 2500.0 + 25.0, 50.0)
        if frequency_grid_hz is None
        else np.asarray(frequency_grid_hz, dtype=float)
    )
    frequencies = np.zeros(templates.shape[0], dtype=float)
    if templates.shape[0] not in (1, 2):
        raise ValueError("one or two sources required")
    updates = (0, 1, 1, 0) if templates.shape[0] == 2 else (0,)
    for source in updates:
        best = None
        for frequency in grid:
            trial = frequencies.copy()
            trial[source] = frequency
            design = _design(
                templates[:, :, train_mask],
                sample_indices[train_mask],
                trial,
                sample_rate_hz,
            )
            amplitudes, sse, condition = _solve(design, response[train_mask])
            candidate = (sse, abs(frequency), frequency, amplitudes, condition)
            if best is None or candidate[:3] < best[:3]:
                best = candidate
        assert best is not None
        frequencies[source] = best[2]
    train_design = _design(
        templates[:, :, train_mask], sample_indices[train_mask], frequencies, sample_rate_hz
    )
    amplitudes, train_sse, condition = _solve(train_design, response[train_mask])
    held_design = _design(
        templates[:, :, ~train_mask], sample_indices[~train_mask], frequencies, sample_rate_hz
    )
    residual = response[~train_mask] - held_design @ amplitudes
    return JointTemplateFit(
        residual_cfo_hz=tuple(float(value) for value in frequencies),
        amplitudes=tuple(complex(value) for value in amplitudes),
        train_sse=train_sse,
        held_sse=float(np.vdot(residual, residual).real),
        held_sample_count=int((~train_mask).sum()),
        gram_condition=float(np.linalg.cond(train_design.conj().T @ train_design)),
        held_gram_condition=float(np.linalg.cond(held_design.conj().T @ held_design)),
        train_rank=int(np.linalg.matrix_rank(train_design)),
        held_rank=int(np.linalg.matrix_rank(held_design)),
    )
