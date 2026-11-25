from importlib import import_module
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture
def study(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("moment_fast_graph")


def test_clock_units_do_not_conflate_edited_preparation_and_graph(study):
    masked, ordinary, projection = (dict(cpu_ns=n, wall_ns=n + 1) for n in (10, 20, 30))
    obs = dict(feature_calls=1, derive=dict(cpu_ns=70, wall_ns=71), moment_preserving=dict(clocks=dict(
        held_odd_proposals=masked, ordinary_graph=ordinary, projection=projection)), attempts=[
            dict(graph_points=56, tracks=9, ordinary_graph_with_extraction_and_overlay=dict(cpu_ns=80, wall_ns=81),
                 overlay=dict(cpu_ns=4, wall_ns=5))])
    graph = dict(calls=1, assigned=56, tracks=9, graph_cpu_ns=65, graph_elapsed_ns=66,
                 edge_cpu_ns=15, edge_elapsed_ns=16)
    pub = {"ports": {"graph": dict(enabled=True, sources=study.FAST_PINS, graph=graph)}, "source_sha256": {
        "reports/ALGO08/v3/exact_graph_execution.py": study.PINS["exact_graph_execution.py"]}}
    result = study.historical(obs, pub)
    assert result["ordinary_graph"] == ordinary
    assert result["edited_inner"] == dict(cpu_ns=65, wall_ns=66)
    assert result["edited_outer"] == dict(cpu_ns=80, wall_ns=81)
    with pytest.raises(ValueError, match="positive integer nanoseconds"):
        study.read_clock(dict(cpu_ns=True, wall_ns=4))
    pub["ports"]["graph"]["enabled"] = False
    with pytest.raises(ValueError, match="pinned fast port"):
        study.historical(obs, pub)


def test_graph_certificate_binds_dtype_scalar_sign_and_order(study):
    item = dict(members=["x", "y"], times=np.array([0., -0.]), slope=np.float64(-0.))
    same = dict(item, times=item["times"].copy())
    assert study.freeze(item) == study.freeze(same)
    assert study.freeze(item) != study.freeze(dict(item, times=item["times"][::-1]))
    assert study.freeze(item) != study.freeze(dict(item, times=item["times"].astype(np.float32)))
    assert study.freeze(item) != study.freeze(dict(item, slope=0.))
    assert study.freeze(item) != study.freeze(dict(item, members=["y", "x"]))


def test_exact_edit_comparison_counts_ids_records_and_values_separately(study):
    invariant = dict(graph_sha256=dict(masked="a", ordinary="b"))
    stock = dict(invariants=invariant, sealed_projection_and_rows_exact=True)
    fast = dict(invariants=dict(graph_sha256=dict(masked="a", ordinary="c")), sealed_projection_and_rows_exact=False)
    result = study.compare((stock, {"a": 1, "b": 2}, {"a": -1., "b": 0.}),
                           (fast, {"a": 3, "c": 4}, {"a": -2., "c": 0.}))
    assert result["full_graph_equal"] == dict(masked=True, ordinary=False)
    assert result["proposal_id_diff"] == result["projected_id_diff"] == 2
    assert result["proposed_record_diff"] == result["applied_value_diff"] == 1


def test_complete_graph_ports_apply_in_publication_order_and_require_native_calls(study):
    full = import_module("moment_fast_graph_full")
    events = []

    @contextmanager
    def graph(*, enabled, audit):
        events.append(("graph", enabled))
        yield
        audit["graph"] = {"calls": 1}

    @contextmanager
    def native(library, *, required):
        assert library == full.LIBRARY and required
        events.append("native")
        yield dict(native_paths=9, packed_lanes=1, pack_ns=2, search_ns=3)

    port = SimpleNamespace(graph_execution=graph)
    audit_stock, audit_fast = {}, {}
    with full.complete(port, native):
        with port.graph_execution(enabled=False, audit=audit_stock):
            pass
        with port.graph_execution(enabled=True, audit=audit_fast):
            pass
    assert events == [("graph", False), "native", ("graph", True)]
    assert audit_stock == {"graph": {"calls": 1}}
    assert full.used_native(dict(graph_ports={"ordinary": audit_fast, "masked": audit_fast}))
    audit_fast["native_paths"]["reference_paths"] = 1
    assert not full.used_native(dict(graph_ports={"ordinary": audit_fast, "masked": audit_fast}))
