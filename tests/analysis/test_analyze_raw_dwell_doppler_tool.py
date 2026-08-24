from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from leo.analysis.starlink.templates import StarlinkEdge
from leo.contracts.digests import canonical_digest


def _tool() -> ModuleType:
    path = Path(__file__).parents[2] / "tools" / "analyze_raw_dwell_doppler.py"
    spec = importlib.util.spec_from_file_location("analyze_raw_dwell_doppler_tool", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _scan() -> dict[str, object]:
    detections = []
    for index, cfo_hz in enumerate((102_000.0, 101_900.0, 101_800.0)):
        detections.append(
            {
                "sample_start": 2_500_000 + 50_000 * index,
                "time_s": 1.0 + 0.02 * index,
                "candidates": [
                    {
                        "rank": 0,
                        "local_epoch_sample": 300 + index,
                        "scores": [
                            {
                                "method": "glrt64",
                                "tracking_cfo_hz": cfo_hz,
                                "exact_score": 0.7,
                                "control_score": 0.04,
                                "margin": 0.66,
                            }
                        ],
                    }
                ],
            }
        )
    return {"schema_version": 3, "probe_samples": 50_000, "detections": detections}


def _source_id(sample_start: int) -> str:
    return canonical_digest({"sample_start": sample_start, "candidate_rank": 0, "method": "glrt64"})


def test_track_reacquisition_uses_exact_raw_sources_not_canonical_alias() -> None:
    tool = _tool()
    scan = _scan()
    observations = tuple(
        SimpleNamespace(
            observation_id=f"canonical-{index}",
            time_s=1.0 + 0.02 * index,
            component_cfo_hz=783_818.0 - 100.0 * index,
            source_observation_ids=(_source_id(2_500_000 + 50_000 * index),),
        )
        for index in range(3)
    )
    branch = SimpleNamespace(
        branch_id="branch",
        observation_ids=tuple(item.observation_id for item in observations),
        start_s=1.0,
        end_s=1.04,
        model=SimpleNamespace(
            reference_time_s=1.0,
            coefficients_hz=(-5_000.0, 783_818.0),
            residual_rms_hz=10.0,
            mad_scale_hz=8.0,
        ),
    )
    bank = SimpleNamespace(branches=(branch,), observations=observations)

    candidate = tool._track_candidate(
        analysis_root=Path("/analysis"),
        stream_id="stream-0",
        receiver_id=0,
        edge=StarlinkEdge.UPPER,
        scan=scan,
        bank=bank,
        branch_id="branch",
    )

    assert candidate is not None
    assert tuple(probe.source_cfo_hz for probe in candidate.track.probes) == (
        102_000.0,
        101_900.0,
        101_800.0,
    )
    assert candidate.source_alias_maximum_hz < 200_000.0
    assert candidate.track.glrt_coefficients_hz == (-5_000.0, 783_818.0)


def test_track_rank_does_not_depend_on_reported_glrt_rate() -> None:
    tool = _tool()
    scan = _scan()
    observations = tuple(
        SimpleNamespace(
            observation_id=f"canonical-{index}",
            time_s=1.0 + 0.02 * index,
            source_observation_ids=(_source_id(2_500_000 + 50_000 * index),),
        )
        for index in range(3)
    )

    def make(rate_hz_s: float) -> object:
        branch = SimpleNamespace(
            branch_id="same-identity",
            observation_ids=tuple(item.observation_id for item in observations),
            start_s=1.0,
            end_s=1.04,
            model=SimpleNamespace(
                reference_time_s=1.0,
                coefficients_hz=(rate_hz_s, 783_818.0),
                residual_rms_hz=10.0,
                mad_scale_hz=8.0,
            ),
        )
        bank = SimpleNamespace(branches=(branch,), observations=observations)
        return tool._track_candidate(
            analysis_root=Path("/analysis"),
            stream_id="stream-0",
            receiver_id=0,
            edge=StarlinkEdge.UPPER,
            scan=scan,
            bank=bank,
            branch_id="same-identity",
        )

    shallow = make(-1_000.0)
    steep = make(-20_000.0)

    assert shallow is not None and steep is not None
    assert shallow.rank_key == steep.rank_key
