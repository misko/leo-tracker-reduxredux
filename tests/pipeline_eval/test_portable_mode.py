import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import portable_mode_build as mode
from tools.pipeline_eval.qualification import portable_receiver
from tools.pipeline_eval.variants.staggered_native import RfStagger


@pytest.mark.parametrize(
    "selector,chosen", [([], "stock"), (["--detector", "staggered"], "staggered")]
)
def test_existing_manifest_uses_stock_and_new_flag_reaches_dispatch(
    tmp_path, monkeypatch, selector, chosen
):
    source = Path(portable_receiver.__file__)
    app = {"__file__": str(source)}
    exec(compile(mode.entry(source.read_text()), str(source), "exec"), app)
    before = []
    app["replay"] = lambda *args: before.append(args[-1])
    manifest = tmp_path / "explicit.json"
    manifest.write_text("{}")
    monkeypatch.setattr(
        sys, "argv", ["receive.py", str(manifest), "--out", str(tmp_path / "new"), *selector]
    )
    app["main"]()
    assert before == [chosen]


def test_packaged_gate_advances_only_valid_visits_and_scopes_by_exact_rf(monkeypatch):
    import json

    bridge = SimpleNamespace(
        encoded=lambda data: json.dumps(data, sort_keys=True),
        _probe=lambda *args: None,
        _from_native=lambda *args: None,
    )
    monkeypatch.setitem(sys.modules, "native_bridge", bridge)
    app = {"MAIN": 6, "HELPER": 7}
    exec(compile(mode.packet_source(), "staggered_packets.py", "exec"), app)
    state = RfStagger()
    choices = []

    def mixed(_samples, lane, *, trace):
        assert trace
        choices.append(lane)
        return dict(rows=[dict(receiver_id=i, candidates=[]) for i in range(2)]), dict(
            fifth_lane=lane, lanes=[dict(cpu=6), dict(cpu=7)]
        )

    def analyze(window, receivers, *_args, detector):
        valid = window.acquisition["valid"]
        if valid:
            detector(window, receivers)
        return SimpleNamespace(
            sample_start=0,
            sample_end=2,
            generation=1,
            status="processed" if valid else "invalid_capture",
            reason="test",
            rf_mapping_authority="hypothesis",
        )

    for visit, (rf, valid) in enumerate(
        ((10, True), (10, False), (20, True), (10, True), (20, True))
    ):
        window = SimpleNamespace(
            acquisition=dict(global_visit=visit, valid=valid),
            target=dict(rf_center_hz=rf),
            samples=np.zeros(8, dtype=np.int16),
            sequence=visit,
            iq_sha256="fixture",
        )
        # The exact runtime gate supplies projected probe dictionaries only on valid visits.
        bridge._probe = lambda _w, rx, _cs: dict(receiver_id=rx, candidates=[])
        _, row = app["run_visit"](
            (0, window, None, None), state, SimpleNamespace(mixed=mixed), analyze, None
        )
        assert ("fifth_lane" in row) is valid
    assert choices == [0, 0, 1, 1]
