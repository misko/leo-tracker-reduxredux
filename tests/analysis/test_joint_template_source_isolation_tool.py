from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_PATH = Path(__file__).parents[2] / "tools/research/joint_template_source_isolation.py"
_SPEC = importlib.util.spec_from_file_location("joint_template_source_isolation", _PATH)
assert _SPEC and _SPEC.loader
tool = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = tool
_SPEC.loader.exec_module(tool)


def _case(second_amplitude: complex) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    rng = np.random.default_rng(21)
    size = 2_000
    indices = np.arange(size)
    groups = indices // 250
    bases = np.vstack([np.exp(2j * np.pi * indices / 37), np.exp(2j * np.pi * indices / 53)])
    tone_offsets = np.arange(8)[:, None] * indices[None, :] / 997
    templates = bases[:, None, :] * np.exp(2j * np.pi * tone_offsets)[None, :, :]
    first_weights = np.linspace(0.2, 0.9, 8) * np.exp(0.2j * np.arange(8))
    second_weights = second_amplitude * np.linspace(0.9, 0.3, 8)
    response = first_weights @ templates[0] + second_weights @ templates[1]
    response += 0.03 * (rng.normal(size=size) + 1j * rng.normal(size=size))
    return response, templates, indices, tool.seeded_group_split(groups)


def test_two_sources_improve_held_prediction_over_single_source() -> None:
    response, templates, indices, train = _case(0.8 - 0.2j)
    grid = np.array([0.0])
    joint = tool.fit_templates(
        response, templates, indices, train, sample_rate_hz=2_500_000, frequency_grid_hz=grid
    )
    single = tool.fit_templates(
        response, templates[:1], indices, train, sample_rate_hz=2_500_000, frequency_grid_hz=grid
    )
    assert joint.held_sse < 0.02 * single.held_sse


def test_one_source_does_not_manufacture_material_held_gain() -> None:
    response, templates, indices, train = _case(0.0j)
    grid = np.array([0.0])
    joint = tool.fit_templates(
        response, templates, indices, train, sample_rate_hz=2_500_000, frequency_grid_hz=grid
    )
    single = tool.fit_templates(
        response, templates[:1], indices, train, sample_rate_hz=2_500_000, frequency_grid_hz=grid
    )
    relative_gain = (single.held_sse - joint.held_sse) / single.held_sse
    assert relative_gain < 0.01


def test_seeded_split_keeps_groups_whole() -> None:
    groups = np.repeat(np.arange(8), 250)
    mask = tool.seeded_group_split(groups)
    assert all(np.unique(mask[groups == group]).size == 1 for group in np.unique(groups))
    assert mask.sum() == 1_000


def test_held_response_cannot_change_training_fit() -> None:
    response, templates, indices, train = _case(0.8j)
    changed = response.copy()
    changed[~train] *= 100j
    kwargs = dict(sample_rate_hz=2_500_000, frequency_grid_hz=np.array([-50.0, 0.0, 50.0]))
    first = tool.fit_templates(response, templates, indices, train, **kwargs)
    second = tool.fit_templates(changed, templates, indices, train, **kwargs)
    assert first.residual_cfo_hz == second.residual_cfo_hz
    assert first.amplitudes == second.amplitudes
    assert first.train_sse == second.train_sse


def test_tone_synthesis_matches_template_and_rational_cadence() -> None:
    from leo.analysis.starlink.templates import qin_edge_pilot_frame
    from tools.research.replay_joint_pilot_isolation import FS, tones

    waveform = tones(0, 0).sum(axis=0)
    frame = qin_edge_pilot_frame(FS, "upper")
    for k in (0, 1, 2, 10):
        start = round(k * FS / 750)
        assert np.allclose(waveform[start : start + len(frame)], frame, atol=1e-6)
    frequency = 123456.0
    carrier = np.exp(2j * np.pi * frequency * np.arange(len(waveform)) / FS)
    assert np.allclose(tones(0, frequency).sum(axis=0), waveform * carrier)
