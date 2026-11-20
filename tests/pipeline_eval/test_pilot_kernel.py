from copy import deepcopy

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.qualification import pilot_kernel_eval, pilot_kernel_positions
from tools.pipeline_eval.variants import anchor_grid, anchor_receiver, pilot_kernel


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    directory = tmp_path_factory.mktemp("pilot-kernel")
    control, candidate = directory / "control.so", directory / "tiled.so"
    anchor_receiver.compile_filter(control)
    pilot_kernel.compile_filter(candidate)
    return anchor_grid.native_grid(control), anchor_grid.native_grid(candidate)


@pytest.mark.parametrize(
    "sample_rate,edge", [(2_500_000, "lower"), (5_000_000, "upper"), (10_000_000, "lower")]
)
@pytest.mark.parametrize("epoch_count", [7, 16, 53])
def test_tiled_grid_keeps_frame_support_and_tail(kernels, sample_rate, edge, epoch_count):
    control, tiled = kernels
    rng = np.random.default_rng(771)
    count = round(sample_rate / 750) + 128
    iq = (rng.normal(size=count) + 1j * rng.normal(size=count)) * 32_000
    template = qin_edge_pilot_frame(sample_rate, edge)
    args = (iq, template, sample_rate, (-220_000.0, 0.0, 100_000.0), (2, 6, 22), epoch_count)
    np.testing.assert_allclose(tiled(*args), control(*args), rtol=0, atol=2e-7)


def test_zero_energy_and_empty_filter_grid(kernels):
    _, tiled = kernels
    rate = 2_500_000
    iq = np.zeros(3_500, dtype=np.complex64)
    template = qin_edge_pilot_frame(rate, "lower")
    np.testing.assert_array_equal(tiled(iq, template, rate, (0,), (2,), 35), np.zeros((1, 35)))
    assert tiled(iq, template, rate, (), (2,), 35) == ()


def test_peak_audit_distinguishes_keys_from_rounding():
    control = [((0.5, 12, -5.0), (0.49, 20, 5.0))]
    same_keys = [((0.50000001, 12, -5.0), (0.49000003, 20, 5.0))]
    assert pilot_kernel_eval._compare_peaks(control, same_keys) == (True, pytest.approx(3e-8))
    assert pilot_kernel_eval._compare_peaks(control, [same_keys[0][::-1]]) == (False, None)
    assert pilot_kernel_eval._compare_peaks(control, []) == (False, None)
    assert pilot_kernel_eval._compare_peaks([], []) == (True, 0.0)
    assert [pilot_kernel_eval.alternating_order(2, i) for i in range(3)] == [
        ("control", "tiled"),
        ("tiled", "control"),
        ("control", "tiled"),
    ]


def test_composites_preserve_observations_and_bind_each_kernel():
    probe = dict(visit_index=2, receiver_id=0, valid_start_counter=200, candidates=[{"score": 0.1}])
    archived = dict(provenance={"run_id": "capture"}, source={"probes": [probe]})
    measurement = dict(
        producer={"run_id": "capture"},
        source_sha256={"grid": "grid", "evaluation": "evaluation"},
        library_sha256={"control": "control", "tiled": "tiled"},
        archive_audit=dict(
            archive_sha256="archive", archive_exclusions_equal=True, different_probe_keys=[]
        ),
        rows=[
            dict(
                visit=2,
                sample_start=200,
                iq_sha256="iq",
                policy_status="processed",
                equal_status=True,
                equal_payload=True,
                equal_coarse_peak_keys=True,
                production=[probe],
                native=[deepcopy(probe)],
            )
        ],
    )
    old, change_old = pilot_kernel_positions.compose(archived, measurement, "control")
    new, change_new = pilot_kernel_positions.compose(archived, measurement, "tiled")
    assert change_old == change_new == 0
    assert old["source"]["probes"] == new["source"]["probes"] == archived["source"]["probes"]
    assert old["provenance"]["scope"] == new["provenance"]["scope"]
    assert old["provenance"]["run_id"] != new["provenance"]["run_id"]
    measurement["rows"][0]["native"][0]["candidates"][0]["score"] = 0.2
    with pytest.raises(ValueError, match="differ"):
        pilot_kernel_positions.compose(archived, measurement, "tiled")
