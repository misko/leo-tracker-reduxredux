from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "reports"
        / "figures"
        / "2026_09_24_dual_capture_phase_random"
        / "replay.py"
    )
    spec = importlib.util.spec_from_file_location("september24_random_phase_replay", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _summary_tool() -> ModuleType:
    path = (
        Path(__file__).parents[2]
        / "reports"
        / "figures"
        / "2026_09_24_dual_capture_phase_random"
        / "summarize.py"
    )
    spec = importlib.util.spec_from_file_location("september24_random_phase_summary", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_dwell_seed_is_reproducible_and_visit_specific() -> None:
    tool = _tool()

    first = tool.dwell_seed("scan-fw-example", 17)

    assert first == tool.dwell_seed("scan-fw-example", 17)
    assert first != tool.dwell_seed("scan-fw-example", 18)
    assert first != tool.dwell_seed("scan-fw-other", 17)
    assert 0 <= first < 2**32


def test_replay_geometry_validator_accepts_supported_rates() -> None:
    tool = _tool()

    for sample_rate_hz in (2_500_000, 15_000_000):
        tool.validate_capture_geometry(
            SimpleNamespace(sample_rate_hz=sample_rate_hz, receiver_ids=(0, 1)),
            "scan-fw-example",
        )

    with pytest.raises(ValueError, match="outside the frozen dual-RX rate cohorts"):
        tool.validate_capture_geometry(
            SimpleNamespace(sample_rate_hz=10_000_000, receiver_ids=(0, 1)),
            "scan-fw-example",
        )


def test_carrier_seed_uses_only_whole_training_group_probes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()

    def probe(start: int, left: float, right: float) -> SimpleNamespace:
        return SimpleNamespace(
            start_sample=start,
            seeds=(
                SimpleNamespace(acquired_cfo_hz=left),
                SimpleNamespace(acquired_cfo_hz=right),
            ),
        )

    probes = (
        probe(0, 10.0, 110.0),
        probe(50_000, 20.0, 220.0),
        probe(100_000, 30.0, 930.0),
        probe(250_000, 40.0, 9_040.0),
    )
    monkeypatch.setattr(tool, "relative_phase_probes", lambda dense: probes)
    split = {"group_samples": 100_000, "training_groups": [0, 2]}

    seed, retained = tool.carrier_seed_hz(object(), split, 2_500_000)

    assert seed == pytest.approx(200.0)
    assert [row["group_id"] for row in retained] == [0, 0, 2]
    assert [row["relative_cfo_hz"] for row in retained] == [100.0, 200.0, 9_000.0]


def test_carrier_seed_abstains_without_training_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool = _tool()
    monkeypatch.setattr(tool, "relative_phase_probes", lambda dense: ())

    with pytest.raises(ValueError, match="no paired GLRT carrier seed"):
        tool.carrier_seed_hz(
            object(), {"group_samples": 100_000, "training_groups": [0]}, 2_500_000
        )


def test_v6_numerical_view_preserves_complete_phase_blind_pairs() -> None:
    tool = _tool()
    configuration = tool.Feature103AnalysisConfigurationV3(
        sample_rate_hz=2_500_000,
        probe_stride_ms=120,
    )

    def candidate(cfo: float, margin: float, *, status: str = "complete") -> SimpleNamespace:
        return SimpleNamespace(
            epoch_sample=1234,
            fractional_epoch_status=status,
            fractional_epoch_offset_samples=0.25 if status == "complete" else None,
            acquired_cfo_hz=cfo,
            fractional_tracking_cfo_hz=cfo + 10.0 if status == "complete" else None,
            fractional_margin=margin if status == "complete" else None,
        )

    analysis = SimpleNamespace(
        probes=(
            SimpleNamespace(
                receiver_id=0,
                probe_index=0,
                candidates=(candidate(100.0, 0.4), candidate(500.0, 0.9, status="failed")),
            ),
            SimpleNamespace(
                receiver_id=1,
                probe_index=0,
                candidates=(candidate(130.0, 0.5),),
            ),
        )
    )
    target = SimpleNamespace(edge="lower")

    view = tool._phase_blind_view(
        analysis,
        configuration,
        target_index=0,
        target=target,
    )

    assert tool.relative_phase_priority(view) == pytest.approx(0.4)
    assert len(tool.relative_phase_probes(view)) == 1
    assert [len(probe.candidates) for probe in view.probes] == [1, 1]


def test_summary_rows_retain_abstentions_in_the_selected_denominator() -> None:
    tool = _summary_tool()
    document = {
        "sessions": [
            {
                "session_id": "scan-fw-example",
                "radio_id": "radio_pluto_test",
                "visits": [
                    {
                        "visit_index": 3,
                        "phase_blind_priority": 4.0,
                        "state": "abstained",
                        "reason": "training evidence unavailable",
                    },
                    {
                        "visit_index": 9,
                        "phase_blind_priority": 3.0,
                        "state": "replayed",
                        "channel": 2,
                        "edge": "lower",
                        "random_phase": {
                            "supported": True,
                            "band_phase_resultant": 0.95,
                            "tracked_coherence": 0.2,
                            "wrong_pair_coherence": 0.01,
                            "split": {"held_groups": [1, 4]},
                        },
                    },
                ],
            }
        ]
    }

    rows = tool.dwell_rows(document)
    aggregate = tool._aggregate(rows)

    assert aggregate["selected_count"] == 2
    assert aggregate["replayed_count"] == 1
    assert aggregate["abstained_count"] == 1
    assert aggregate["supported_fraction_of_selected"] == pytest.approx(0.5)
    assert rows[1]["held_group_count"] == 2
