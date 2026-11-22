import gc

import pytest

from tools import algo08_position
from tools.pipeline_eval.variants.algo08_gc_audit import measure_collector


def test_measures_collection_in_innermost_phase():
    def unreachable_cycle():
        link = []
        link.append(link)

    gc.collect(0)
    with measure_collector() as audit:
        with audit.scope("prepare_scan"), audit.scope("parse_catalogue"):
            unreachable_cycle()
            gc.collect(0)
        assert audit.phase == "solver_other"

    collected = audit.collections["parse_catalogue"][0]
    assert collected["calls"] >= 1
    assert collected["collected"] >= 1
    assert collected["cpu_ns"] > 0
    assert collected["wall_ns"] > 0
    assert collected["uncollectable"] == 0
    assert audit.collections["prepare_scan"][0]["calls"] == 0


def test_cleans_up_callback_and_bindings_when_operation_raises(monkeypatch):
    def fail():
        raise ValueError("invalid catalogue")

    monkeypatch.setattr(algo08_position, "prepare_native_scan", fail)
    callbacks = tuple(gc.callbacks)
    prior = gc.isenabled(), gc.get_threshold(), gc.get_debug()
    with pytest.raises(ValueError, match="invalid catalogue"):
        with measure_collector() as audit:
            algo08_position.prepare_native_scan()

    assert audit.phases["prepare_scan"]["calls"] == 1
    assert audit.phase == "solver_other"
    assert tuple(gc.callbacks) == callbacks
    assert (gc.isenabled(), gc.get_threshold(), gc.get_debug()) == prior
    assert algo08_position.prepare_native_scan is fail


def test_deferred_preparation_releases_cycles_and_restores_state_on_error(monkeypatch):
    finalized = []
    expected = ValueError("invalid catalogue")

    class Cycle:
        def __init__(self):
            self.link = self

        def __del__(self):
            finalized.append("released")

    def prepare():
        assert not gc.isenabled()
        Cycle()
        assert not finalized
        raise expected

    monkeypatch.setattr(algo08_position, "prepare_native_scan", prepare)
    original = gc.isenabled(), gc.get_threshold(), gc.get_debug()
    with measure_collector(defer_preparation=True) as audit:
        with pytest.raises(ValueError) as error:
            algo08_position.prepare_native_scan()

    assert error.value is expected
    assert finalized == ["released"]
    assert (gc.isenabled(), gc.get_threshold(), gc.get_debug()) == original
    generation = audit.collections["preparation_collection"][0]
    assert generation["calls"] == 1
    assert generation["collected"] >= 1


def test_skips_deferral_with_initially_disabled_collector(monkeypatch):
    monkeypatch.setattr(algo08_position, "prepare_native_scan", gc.isenabled)
    original = gc.isenabled()
    gc.disable()
    try:
        with measure_collector(defer_preparation=True) as audit:
            assert not algo08_position.prepare_native_scan()
        assert not gc.isenabled()
        assert audit.phases["preparation_collection"]["calls"] == 0
    finally:
        if original:
            gc.enable()
