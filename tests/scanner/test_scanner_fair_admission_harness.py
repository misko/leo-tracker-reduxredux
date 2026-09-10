import pytest

from tests.scanner.fair_admission_harness import ORIGIN, Geometry, build, run
from tools.scanner_sampled_admission_model import simulate


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    return build(tmp_path_factory.mktemp("gated-fair-sdk") / "build")


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("cost", [75, 170])
def test_real_sdk_gated_completion_inventory_and_sample_grid(binaries, tmp_path, rate, cost):
    dwell = rate * 120 // 1000
    geometry = [Geometry(ORIGIN + i * dwell, ORIGIN + (i + 1) * dwell, i % 8) for i in range(40)]
    result = run(*binaries, tmp_path / "run", rate, geometry, [cost] * len(geometry))
    assert result["records"] == 40
    if cost == 75:
        assert len(result["checks"]) == 40
    else:
        assert 0 < len(result["checks"]) < 40
        assert {c["target"] for c in result["checks"]} == set(range(8))
    assert all(
        c["completed_ms"] <= c["harvested_ms"] < c["completed_ms"] + 20 for c in result["checks"]
    )
    assert not result["protection"]["watchdog_trips"]
    expected = simulate(geometry, rate, [cost] * len(geometry))
    assert [(c["visit"], c["started_ms"]) for c in result["checks"]] == [
        (c["visit"], c["started_ms"]) for c in expected["checks"]
    ]


@pytest.mark.parametrize("rate", [2500000, 5000000])
def test_gated_uneven_schedule_with_worker_and_owner_jitter(binaries, tmp_path, rate):
    pattern = [0, 2, 3, 0, 2, 3, 0, 2, 3, 1, 4, 5, 6, 7]
    step = rate * 126 // 1000
    dwell = rate * 120 // 1000
    geometry = [
        Geometry(ORIGIN + i * step, ORIGIN + i * step + dwell, pattern[i % len(pattern)])
        for i in range(112)
    ]
    costs = [75, 150, 190, 210, 90, 170, 160] * 16
    result = run(
        *binaries, tmp_path / "run", rate, geometry, costs, owner_jitter_ms=(0, 3, 8, 1, 9, 5)
    )
    assert result["records"] == len(geometry)
    assert 0 < len(result["checks"]) < len(geometry)
    assert {c["target"] for c in result["checks"]} == set(range(8))
    assert all(
        c["completed_ms"] <= c["harvested_ms"] < c["completed_ms"] + 29 for c in result["checks"]
    )
    expected = simulate(geometry, rate, costs, owner_jitter_ms=(0, 3, 8, 1, 9, 5))
    assert [(c["visit"], c["started_ms"]) for c in result["checks"]] == [
        (c["visit"], c["started_ms"]) for c in expected["checks"]
    ]
