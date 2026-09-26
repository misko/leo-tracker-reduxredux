from __future__ import annotations

import importlib.util
from pathlib import Path

PATH = (
    Path(__file__).parents[2]
    / "reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/acquisition/replay_acquisition.py"
)
SPEC = importlib.util.spec_from_file_location("replay_acquisition", PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_pins_corrected_revisions_and_source() -> None:
    assert MODULE.PRODUCER_REVISION == "2c30eaf50064623a666e1c078c56a02cb3223a70"
    assert MODULE.PINNED_REPLAY_REVISION == "e1a24b200d4bb68d4f38484dc591e9b9616a2e70"
    assert MODULE.INPUT_MANIFEST_SHA256.startswith("sha256:")
    assert MODULE.AUTHORITATIVE_SELECTION_SHA256 == (
        "sha256:b73c0d5322a6a70c6ee851ee80ad99ef62ca13b190ae4bdeb35ce95ce2030115"
    )


def test_dense_runner_uses_native_six_probe_schedule() -> None:
    text = PATH.with_name("run_primary_acquisition.py").read_text()
    assert "sample_rate_hz=10_000_000" in text
    assert "probe_stride_ms=20" in text
