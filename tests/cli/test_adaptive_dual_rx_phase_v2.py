from __future__ import annotations

import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

from leo.analysis.starlink.adaptive_dual_rx_geometry_phase import SPEED_OF_LIGHT_M_S
from tests.application.test_adaptive_dual_rx_geometry_v2 import _binding, _inputs
from tests.storage.test_adaptive_dual_rx_phase_v2_store import digest, visit

_SPEC = importlib.util.spec_from_file_location(
    "adaptive_dual_rx_phase_v2_cli",
    Path(__file__).parents[2] / "src/leo/cli/adaptive_dual_rx_phase_v2.py",
)
assert _SPEC is not None and _SPEC.loader is not None
subject = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(subject)


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return None


def test_cli_uses_bound_calibration_to_publish_geometry_comparison(monkeypatch, tmp_path) -> None:
    geometry_binding = _binding()
    inputs = _inputs(geometry_binding)
    row = inputs.directions[0]
    predicted = 2 * math.pi * 0.08 * row.high_rf_hz * 0.1 / SPEED_OF_LIGHT_M_S
    hardware = 2 * math.pi * 3.2e-9 * (row.high_rf_hz - row.low_rf_hz) + 0.13
    measured = math.atan2(math.sin(predicted + hardware), math.cos(predicted + hardware))
    phase_visit = visit(0).model_copy(
        update={
            "hypotheses": (
                visit(0).hypotheses[0].model_copy(update={"wrapped_high_minus_low_rad": measured}),
            )
        }
    )
    capture = SimpleNamespace(
        receipt=SimpleNamespace(session_id="scan-hop-phase-v2"),
        created_utc_ns=1_799_999_999_000_000_000,
        finalized_utc_ns=1_800_000_100_000_000_000,
        receiver_geometry=geometry_binding,
        timing=SimpleNamespace(
            qualified=True,
            first_sample_estimate_utc_ns=1_800_000_000_000_000_000,
        ),
    )
    inspected = SimpleNamespace(manifest=capture, manifest_sha256=digest("1"))
    binding = SimpleNamespace(
        input_manifest_sha256=digest("1"),
        sha256=digest("2"),
        configuration=SimpleNamespace(receiver_ids=(0, 1)),
    )
    finalized = {}

    class Captures:
        def __init__(self, *_args, **_kwargs):
            pass

        def inspect(self, _session_id):
            return inspected

        def close(self):
            pass

    class Job:
        def manifest(self):
            return SimpleNamespace(model_dump=lambda **_kwargs: {"sealed": True})

        def completed_visits(self):
            return (0,)

    class Analyses:
        def __init__(self, *_args, **_kwargs):
            pass

        def job(self, _binding):
            return _Context(Job())

        def close(self):
            pass

    class Inputs:
        def __init__(self, _captures):
            pass

        def source(self, _session_id):
            return _Context(object())

    class Phases:
        def __init__(self, *_args, **_kwargs):
            pass

        def completed_visits(self, *_args):
            return (0,)

        def read_visit(self, *_args):
            return phase_visit

        def finalize(self, **kwargs):
            finalized.update(kwargs)
            return SimpleNamespace(model_dump=lambda **_kwargs: {"state": "ready"})

        def close(self):
            pass

    monkeypatch.setattr(subject, "AdaptiveHopIqStore", Captures)
    monkeypatch.setattr(subject, "AdaptiveHopAnalysisStore", Analyses)
    monkeypatch.setattr(subject, "AdaptiveHopAnalysisInputStore", Inputs)
    monkeypatch.setattr(subject, "AdaptiveDualRxPhaseStoreV2", Phases)
    monkeypatch.setattr(subject, "GeometryBoundAdaptiveHopIqManifestV6", object)
    monkeypatch.setattr(subject, "bind_actual_visit_analysis", lambda *_args, **_kwargs: binding)

    result = subject.run(
        tmp_path,
        "scan-hop-phase-v2",
        probe_stride_ms=120,
        maximum_visits=20,
        geometry_input=inputs,
    )

    assert result["state"] == "complete"
    assert finalized["geometry_phase_state"] == "conditionally_unique"
    assert finalized["geometry"].point_count == 1
    assert finalized["geometry"].residual_rms_rad < 1e-12
    assert finalized["png"].startswith(b"\x89PNG\r\n\x1a\n")
