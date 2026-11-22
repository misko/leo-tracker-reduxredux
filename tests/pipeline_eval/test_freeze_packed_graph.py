from importlib import import_module

trial = import_module("reports.ALGO08.single-core-2x.freeze_packed_graph")


def test_changing_detector_or_relocating_libraries_preserves_fixed_settings():
    parent = dict(sources={"solver.py": "a"}, solver="screened-tiled-finish", detector="/old",
                  detector_sha256="old", graph_path={"library": "/old/graph.so", "sha256": "abc"})
    new = dict(parent, detector="/new", detector_sha256="new",
               graph_path={"library": "/new/graph.so", "sha256": "abc"})
    assert trial.fixed_options(parent) == trial.fixed_options(new)
    for changed in (dict(sources={}), dict(solver="stock"), dict(regional_veto=True),
                    dict(graph_path={"library": "/new/graph.so", "sha256": "replacement"})):
        assert trial.fixed_options(parent) != trial.fixed_options(new | changed)
