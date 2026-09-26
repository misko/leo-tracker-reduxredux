import csv
import importlib.util
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/single-track/multitrack/data"


def test_real_multitrack_observations_are_synchronized_and_self_describing():
    metadata = json.loads((DATA / "metadata.json").read_text())
    rows = list(csv.DictReader((DATA / "observations.csv").open()))
    assert metadata["real_data"] is True
    assert metadata["phase_selection"] is False
    assert metadata["row_count"] == len(rows) >= 250
    assert metadata["chosen_visits"] == [14, 52, 73, 74, 1074, 1711, 1734, 1735]

    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["group_id"], row["window_start_sample"])].append(row)
        assert -np.pi <= float(row["phase_rad"]) <= np.pi
        assert 0 <= float(row["weight"]) <= 1
        assert int(row["frame_count"]) > 0
    for observations in grouped.values():
        assert len(observations) >= 2
        assert len({row["time_s"] for row in observations}) == 1
        assert len({row["device_counter"] for row in observations}) == 1
        assert len({row["common_rx1_minus_rx0_authority_hz"] for row in observations}) == 1
        assert len({row["alias_group"] for row in observations}) == len(observations)

    archive = np.load(DATA / "observations.npz")
    assert set(archive.files) == set(rows[0])
    assert len(archive["phase_rad"]) == len(rows)


def test_builder_selection_is_phase_blind():
    source = (DATA / "build_observations.py").read_text()
    selection_statement = next(line for line in source.splitlines() if "CHOSEN_VISITS =" in line)
    assert "phase" not in selection_statement
    assert "[14, 52, 73, 74, 1074, 1711, 1734, 1735]" in selection_statement


def test_common_gauge_ignores_mode_specific_rx1_seed_branch():
    spec = importlib.util.spec_from_file_location("multitrack_data_builder", DATA / "build_observations.py")
    assert spec and spec.loader
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)

    calls = []
    class Seed:
        def __init__(self, acquired_cfo_hz, reference_sample):
            self.acquired_cfo_hz = acquired_cfo_hz
            self.reference_sample = reference_sample
    class Observation:
        wrapped_phase_rad = 0.4
        relative_frequency_hz = 0.0
        center_sample = 35_000.0
        resultant_length = 0.9
        independent_frame_count = 5
    class Result:
        observation = Observation()
    class Shared:
        RATE = 10_000_000
        FRAME_RATE_HZ = 750.0
        ReceiverPhaseSeed = Seed
        @staticmethod
        def _epoch(row): return row["epoch"]
        @staticmethod
        def extract_dual_receiver_phase_with_offset_authority_shared_residual(
            iq, rate, edge, epoch, seeds, authority, **kwargs
        ):
            calls.append((authority, kwargs["common_reference_sample"], seeds[1].acquired_cfo_hz))
            return Result()

    iq = np.ones((70_000, 2), dtype=np.complex64)
    left = {"tracking_absolute_baseband_cfo_hz": 100.0, "epoch": 10.0}
    phases = []
    for rx1_seed in (200.0, 57_200.0):
        right = {"tracking_absolute_baseband_cfo_hz": rx1_seed, "epoch": 20.0}
        phases.append(builder._extract_in_common_gauge(
            Shared, iq, "upper", (left, right), 0, 70_000, 682_000.0
        )["phase_rad"])
    assert phases[0] == phases[1]
    assert [call[:2] for call in calls] == [(682_000.0, 35_000.0)] * 2
