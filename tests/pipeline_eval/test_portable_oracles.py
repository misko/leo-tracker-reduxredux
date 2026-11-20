import ast
import json
from hashlib import sha256
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.reference import waveform


def _statements(source):
    return {
        node.targets[0].id if isinstance(node, ast.Assign) else node.name: node
        for node in ast.parse(source).body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef))
        or isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name)
    }


def test_packaged_references_match_their_pinned_sources():
    folder = Path(waveform.__file__).parent
    inventory = json.loads((folder / "pins.json").read_bytes())
    assert inventory["schema"] == 1
    assert set(inventory["modules"]) == {
        p.name for p in folder.glob("*.py") if p.name != "__init__.py"
    }
    for name, pin in inventory["modules"].items():
        raw = (folder / name).read_bytes()
        assert sha256(raw).hexdigest() == pin["sha256"], name
        if name != "waveform.py":
            assert pin["sha256"] == pin["sources"][0]["sha256"], name
            continue
        text = raw.decode()
        nodes = _statements(text)
        assert nodes.keys() == {symbol for source in pin["sources"] for symbol in source["symbols"]}
        for source in pin["sources"]:
            statements = "\n".join(
                ast.get_source_segment(text, nodes[symbol]) for symbol in source["symbols"]
            )
            assert sha256(statements.encode()).hexdigest() == source["statements_sha256"]


def test_packaged_waveform_preserves_gated_reference_search():
    rng = np.random.default_rng(360)
    count = waveform.PROBE_SAMPLES
    samples = 0.08 * (rng.normal(size=count) + 1j * rng.normal(size=count))
    pilot = waveform.qin_edge_pilot_frame(waveform.RATE, "lower")
    counter = 99_907
    for start in np.rint(np.arange(14) * waveform.RATE / 750).astype(int) + 2_991:
        stop = min(start + pilot.size, count)
        angle = 2j * np.pi * 37_000 / waveform.RATE
        samples[start:stop] += pilot[: stop - start] * np.exp(angle * np.arange(start, stop))
    gate = SimpleNamespace(
        phase_us=waveform.phase_at(2_991, counter), frequency=37_000, half_us=2.0, half_hz=2_200.0
    )

    result = waveform.PilotBank("lower").search(samples, counter, (gate,))

    winner = result["winner"]
    assert result["tested_epochs"] == 19
    assert result["scored_epoch_alias_cfo_cells"] == 1_900
    assert winner["passed"]
    assert winner["epoch_sample"] == 2_993
    assert winner["frames"] == 15
    assert winner["cfo_hz"] == winner["alias_cfo_hz"] == pytest.approx(36_843.03977272727)
    assert winner["phase_us"] == pytest.approx(956.6666666666665)
    assert [winner[key] for key in ("exact", "control", "margin")] == pytest.approx(
        [0.9784594032598208, 0.026087265925666212, 0.9523721373341546], abs=1e-12, rel=0
    )
