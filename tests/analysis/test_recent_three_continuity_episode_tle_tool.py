from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tools import report_recent_three_continuity_episode_tle as tool


def _rate_observation(
    *,
    acquisition: str,
    receiver_id: int,
    time_s: float,
    rate_hz_s: float,
    cfo_hz: float,
    phase_sample: float = 100.0,
    train: bool = True,
) -> tool.RateObservation:
    return tool.RateObservation(
        acquisition=acquisition,
        path=f"radio_pluto_5d4d/RX{receiver_id}",
        receiver_id=receiver_id,
        rf_hz=float(tool.D2_SCANNER_RF_HZ),
        utc_ns=int(time_s * 1e9),
        time_s=time_s,
        value_hz_s=rate_hz_s,
        sigma_hz_s=100.0,
        train=train,
        source_kind="test",
        source_id=f"{acquisition}-rx{receiver_id}",
        qualified=True,
        phase_lock_qualified=True,
        cfo_hz=cfo_hz,
        cfo_sigma_hz=20.0,
        source_epoch_sample=0,
        source_probe_start_ms=0,
        absolute_lattice_phase_sample=phase_sample,
        supported_frame_count=55,
        lattice_epoch_utc_ns=int(time_s * 1e9),
        source_product_uri="test.json",
        source_product_sha256="sha256:test",
    )


def test_absolute_lattice_phase_includes_probe_offset_without_rounding_period() -> None:
    assert tool.absolute_lattice_phase_sample(661_017_643_205, 0, 2_416) == pytest.approx(
        2_287 + 2 / 3
    )
    assert tool.absolute_lattice_phase_sample(661_079_533_088, 10, 189) == pytest.approx(
        1_610 + 1 / 3
    )


def test_phase_cluster_selection_is_circular_and_tle_blind() -> None:
    rows = [
        _rate_observation(
            acquisition=f"scan{index}",
            receiver_id=1,
            time_s=float(index),
            rate_hz_s=-3_800.0,
            cfo_hz=-90_000.0,
            phase_sample=phase,
        )
        for index, phase in enumerate((3_320.0, 5.0, 20.0, 590.0), start=1)
    ]

    selected = tool.largest_phase_cluster(rows, maximum_span_samples=40.0)

    assert {item.absolute_lattice_phase_sample for item in selected} == {
        3_320.0,
        5.0,
        20.0,
    }
    assert tool.circular_phase_span_samples(
        [float(item.absolute_lattice_phase_sample) for item in selected]
    ) == pytest.approx(100 / 3)


def test_cfo_continuation_gate_accepts_rx1_and_rejects_rx0_reset() -> None:
    dwell = [
        _rate_observation(
            acquisition="dwell",
            receiver_id=1,
            time_s=59.36,
            rate_hz_s=-3_195.0,
            cfo_hz=-42_820.0,
        )
    ]
    scanner = [
        _rate_observation(
            acquisition="scan01",
            receiver_id=1,
            time_s=73.74,
            rate_hz_s=-3_888.0,
            cfo_hz=-92_479.0,
        ),
        _rate_observation(
            acquisition="scan02",
            receiver_id=1,
            time_s=82.45,
            rate_hz_s=-3_915.0,
            cfo_hz=-125_718.0,
        ),
        _rate_observation(
            acquisition="scan01",
            receiver_id=0,
            time_s=73.74,
            rate_hz_s=-3_742.0,
            cfo_hz=455_371.0,
        ),
        _rate_observation(
            acquisition="scan02",
            receiver_id=0,
            time_s=82.45,
            rate_hz_s=-4_032.0,
            cfo_hz=422_407.0,
        ),
        _rate_observation(
            acquisition="scan03",
            receiver_id=0,
            time_s=90.88,
            rate_hz_s=-3_699.0,
            cfo_hz=389_990.0,
        ),
        _rate_observation(
            acquisition="scan04",
            receiver_id=0,
            time_s=99.37,
            rate_hz_s=-3_877.0,
            cfo_hz=420_059.0,
        ),
    ]

    result = tool.select_cfo_continuations(dwell, scanner)

    assert all(item["accepted"] for item in result[1])
    assert [item["accepted"] for item in result[0]] == [True, True, True, False]
    assert result[0][-1]["innovation_hz"] > 60_000.0


def test_rate_bank_ranking_uses_training_fit_and_per_path_nuisance() -> None:
    observations = [
        _rate_observation(
            acquisition=f"a{index}",
            receiver_id=index % 2,
            time_s=float(index),
            rate_hz_s=10.0 * index + (50.0 if index % 2 else -30.0),
            cfo_hz=0.0,
            train=index < 4,
        )
        for index in range(6)
    ]
    grid = np.linspace(-3.0, 9.0, 121)
    physical = 10.0 * grid
    wrong = -40.0 * grid
    bank = {
        "time_s": grid,
        "rate_by_rf": {
            tool.D2_SCANNER_RF_HZ: np.vstack((physical, wrong)),
        },
        "metadata": [
            {
                "catalog_number": 1,
                "object_name": "right",
                "element_epoch_utc_ns": 0,
                "element_age_s": 0.0,
                "minimum_elevation_deg": 20.0,
                "peak_elevation_deg": 30.0,
                "midpoint_elevation_deg": 25.0,
                "midpoint_range_km": 500.0,
                "midpoint_range_rate_km_s": 0.0,
            },
            {
                "catalog_number": 2,
                "object_name": "wrong",
                "element_epoch_utc_ns": 0,
                "element_age_s": 0.0,
                "minimum_elevation_deg": 20.0,
                "peak_elevation_deg": 30.0,
                "midpoint_elevation_deg": 25.0,
                "midpoint_range_km": 500.0,
                "midpoint_range_rate_km_s": 0.0,
            },
        ],
    }

    ranked = tool.rank_rate_bank(observations, bank, epoch_bound_s=0.3)

    assert ranked[0]["catalog_number"] == 1
    assert ranked[0]["train_rms_hz_s"] == pytest.approx(0.0, abs=1e-10)
    assert ranked[0]["holdout_rms_hz_s"] == pytest.approx(0.0, abs=1e-10)
    assert ranked[0]["path_rate_nuisance_hz_s"] == pytest.approx(
        {
            "radio_pluto_5d4d/RX0": -30.0,
            "radio_pluto_5d4d/RX1": 50.0,
        }
    )


def test_tle_record_reader_compares_exact_lines_and_skips_alpha5(tmp_path: Path) -> None:
    source = tmp_path / "catalog.tle"
    source.write_text(
        "NAME\n"
        "1 57902U 23125A   26236.00000000  .00000000  00000-0  00000-0 0  9999\n"
        "2 57902  53.0000 100.0000 0001000  10.0000 350.0000 15.00000000    01\n"
        "ALPHA\n"
        "1 A0001U 23125B   26236.00000000  .00000000  00000-0  00000-0 0  9999\n"
        "2 A0001  53.0000 100.0000 0001000  10.0000 350.0000 15.00000000    01\n"
    )

    records = tool.tle_records(source)

    assert list(records) == [57902]
    assert records[57902][0].startswith("1 57902")


def test_d2_episode_groups_never_mix_the_two_plutos() -> None:
    for name, definition in tool.GROUPS.items():
        if not name.startswith("D2-"):
            continue
        streams = {path.split("/")[0] for path in definition["members"]}
        assert len(streams) == 1
