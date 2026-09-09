import io

import numpy as np
import pytest
from matplotlib.image import imread

from leo.presentation.adaptive_hop_analysis import (
    adaptive_trajectory_configuration,
    project_adaptive_overview,
    render_adaptive_hop_overview,
)
from leo.scanner.adaptive_hop_presentation import OVERVIEW_ARTIFACTS
from tests.presentation.adaptive_overview_fixtures import full_overview_fixture, overview_fixture


@pytest.mark.parametrize("gate", [0.025, 0.05])
def test_passed_only_association_gate_is_explicit_and_tracks_configured_margin(gate):
    config = adaptive_trajectory_configuration(gate)
    assert config.methods[0].low_gate == config.methods[0].high_gate == gate
    assert config.digest != adaptive_trajectory_configuration(gate + 0.01).digest


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_projection_uses_actual_targets_gaps_fractional_winners_and_all_passed_candidates(
    monkeypatch, rate, mode
):
    binding, manifest, products = overview_fixture(monkeypatch, rate=rate, mode=mode, count=30)
    data = project_adaptive_overview(binding, manifest, iter(products))
    assert data.winners.shape == data.passed.shape == (29 * 22, 4)
    assert not data.passed.flags.writeable and not data.winners.flags.writeable
    assert np.all(data.winners[:, 3] == 0.045) and np.all(data.passed[:, 3] == 1960)
    row = 25 * 22
    assert data.passed[row, 0] == (2 if mode == "adaptive" else 1)
    candidate = products[25].probes[0].candidates[1]
    assert data.passed[row, 2] == candidate.fractional_time_s
    assert candidate.integer_device_sample_counter > 2**53
    assert data.passed[row, 2] > 25 * 0.12
    observations = [o for group in data.observations.values() for o in group]
    assert len(observations) == 58 and all(o.tracking_cfo_hz == 1960 for o in observations)
    assert all(":probe:0:candidate:1" in o.observation_id for o in observations)
    assert data.passed.nbytes == 29 * 22 * 4 * 8


@pytest.mark.parametrize(
    "fault", ["binding", "missing", "duplicate", "reordered", "counts", "tamper"]
)
def test_projection_rejects_incomplete_or_misbound_science(monkeypatch, fault):
    binding, manifest, products = overview_fixture(monkeypatch)
    if fault == "binding":
        manifest = manifest.model_copy(update={"binding_sha256": "sha256:" + "9" * 64})
    if fault == "missing":
        products = products[:-1]
    if fault == "duplicate":
        products = (products[0], products[0])
    if fault == "reordered":
        products = tuple(reversed(products))
    if fault == "counts":
        changed = manifest.visits[0].model_copy(update={"passed_fractional_candidate_count": 0})
        manifest = manifest.model_copy(update={"visits": (changed, manifest.visits[1])})
    if fault == "tamper":
        products = (
            products[0].model_copy(update={"input_manifest_sha256": "sha256:" + "9" * 64}),
            products[1],
        )
    with pytest.raises(ValueError):
        project_adaptive_overview(binding, manifest, iter(products))


@pytest.mark.parametrize("count", [0, 3, 30])
def test_renderer_emits_real_decodable_bound_pngs_and_explicit_associations(monkeypatch, count):
    binding, manifest, products = overview_fixture(monkeypatch, count=count)
    result = render_adaptive_hop_overview(binding, manifest, iter(products))
    assert tuple(result.artifacts) == OVERVIEW_ARTIFACTS
    assert result.selected_observation_count == max(0, count - 1) * 2
    assert 0 <= result.association_count <= 1024
    if count == 30:
        # Passed-only input has no negative tail to estimate a high-score gate.
        # These constant-CFO tracks span multiple visits and must be associated.
        assert result.association_count > 0
    for png in result.artifacts.values():
        image = imread(io.BytesIO(png), format="png")
        assert image.shape[1] == 2480 and image.shape[0] > 1000
        assert binding.session_id.encode() in png
        assert float(image.std()) > 0.02


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_full_300s_maximum_candidate_projection_is_bounded_and_keeps_every_passed_point(rate, mode):
    binding, manifest, products = full_overview_fixture(rate=rate, mode=mode)
    data = project_adaptive_overview(binding, manifest, products())
    count = binding.receipt.complete_visit_count
    assert count > 2200
    assert data.winners.shape == (count * 22, 4)
    assert data.passed.shape == (count * 22 * 16, 4)
    assert data.winners.nbytes + data.passed.nbytes < 30_000_000
    assert sum(len(group) for group in data.observations.values()) == 2 * count
    assert set(data.passed[:, 0]) == set(range(8))
    assert data.passed[-1, 2] > 299
    assert data.passed[-1, 2] < binding.receipt.duty_denominator_sample_count / rate
    expected = 400_000 - 1000 * data.passed[:, 2] + 2 * data.passed[:, 2] ** 2
    expected -= data.passed[:, 1] * 600_000
    expected += data.passed[:, 0] * 10_000 + np.tile(np.arange(16), count * 22) * 4000
    np.testing.assert_allclose(data.passed[:, 3], expected, rtol=1e-14, atol=1e-8)
