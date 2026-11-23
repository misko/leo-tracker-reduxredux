from contextlib import contextmanager
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize("enabled", [True, False])
def test_raw_publication_scopes_the_repair_and_named_fit_together(monkeypatch, enabled):
    here = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
    entry = runpy.run_path(str(here / "unified_short_bootstrap.py"))
    events = []

    @contextmanager
    def isolate():
        events.append("isolate")
        yield
        events.append("restore discovery")

    @contextmanager
    def fit(witness):
        events.append("fit")
        witness["model"] = "signed"
        yield
        events.append("restore fit")

    def publish(*args, **kwargs):
        assert events == (["isolate", "fit"] if enabled else [])
        return {"receipt": {"decision": "complete"}}

    modules = {"joint_publication": dict(configuration=None, run=publish),
               "full_short_run": dict(geographic_projection=None),
               "regional_probe_block_binding": dict(guarded_projection=None),
               "exact_graph_execution": dict(graph_execution=None), "isolated_salvage": dict(binding=isolate),
               "named_survivor_fit": dict(binding=fit)}
    for name, functions in modules.items():
        module = ModuleType(name)
        vars(module).update(functions)
        monkeypatch.setitem(sys.modules, name, module)
    args = SimpleNamespace(named_survivor_finish=enabled, one_pass_web_png=True)
    _, detail = entry["publish_active"](args, None, {}, None, {})
    if enabled:
        assert detail["named_survivor_finish"] == dict(requested=True, paid_final_fit=True)
        assert events == ["isolate", "fit", "restore fit", "restore discovery"]
    else:
        assert "named_survivor_finish" not in detail and not events
