from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def exterior(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    import prepared_exterior

    return prepared_exterior


def test_handoff_requires_original_normalized_graph_root_and_causal_cutoff(exterior, tmp_path):
    tracks = {"metadata": {"causal_cutoff_utc_ns": 42}}
    reader = SimpleNamespace(root=tmp_path)
    causal = object()
    handoff = exterior.PreparedExterior(reader.root, tracks, 42, causal)
    assert handoff.match(tracks, reader) is causal
    assert handoff.match(deepcopy(tracks), reader) is None
    assert handoff.match(tracks, SimpleNamespace(root=tmp_path / "other")) is None
    tracks["metadata"]["causal_cutoff_utc_ns"] += 1
    assert handoff.match(tracks, reader) is None


def test_scoped_handoff_captures_actual_preparation_and_preserves_fresh_fallback(exterior, monkeypatch, tmp_path):
    from sgp4 import api
    from leo.operations import localization_v3_inputs as inputs
    from leo.operations.tle_archive import TleArchiveReader
    from tools import algo08_position
    from tools.pipeline_eval.variants.experimental import regional_bound_guard

    original = {"status": "inputs_prepared", "tracks": {"metadata": {"causal_cutoff_utc_ns": 42}}}
    causal = object()
    explicit = object()
    reader = TleArchiveReader(tmp_path)
    monkeypatch.setattr(api, "accelerated", True)
    monkeypatch.setattr(inputs, "causal_catalogue", lambda *_args, **_kwargs: causal)

    def prepare(*_args):
        assert inputs.causal_catalogue(reader, 42, element_parser=object()) is causal
        return original

    def probe(_tracks, _reader, _region, *, catalogue=None, terminal_only=False):
        return catalogue, terminal_only

    monkeypatch.setattr(algo08_position, "prepare_native_scan", prepare)
    monkeypatch.setattr(algo08_position, "_prepared_values", deepcopy)
    monkeypatch.setattr(regional_bound_guard, "causal_probes", probe)
    with exterior.handoff(reader) as (live, counts, plain):
        entered = algo08_position.prepare_native_scan({}, reader)
        ready = algo08_position._prepared_values(entered)
        normalized = ready["tracks"]
        assert live.tracks is normalized
        assert live.tracks is not original["tracks"]
        assert plain is probe
        assert regional_bound_guard.causal_probes(normalized, reader, None, terminal_only=True) == (causal, True)
        assert regional_bound_guard.causal_probes(entered["tracks"], reader, None) == (None, False)
        assert regional_bound_guard.causal_probes(normalized, reader, None, catalogue=explicit) == (explicit, False)
        assert dict(counts) == dict(prepared_catalogues=1, catalogue_handoff=1, fresh_catalogue=1, existing_catalogue=1)
    assert regional_bound_guard.causal_probes is probe
    assert algo08_position.prepare_native_scan is prepare
