"""Use the complete released Graph port during frozen CFO edit formation."""

from contextlib import contextmanager
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NATIVE_MODULE = "tools/pipeline_eval/variants/experimental/graph_path.py"
PINS = {
    "spec.json": "652f8573e2fdec746dd318849c82992eb7786f014e8dbc393c0352b54e421e46",
    "graph-path.so": "e623daaff9ac9fddc709d26af2a1fecd696aa133568c3d6c0a4d10e6b481d627",
    NATIVE_MODULE: "289bd1b9dbf1559e4610013cdaed619a388e2d4a59c96c1956df42329483478c",
    "tools/pipeline_eval/variants/experimental/graph_path.c":
        "cbbee06c6305f82a096561ae6498ef163786e7c82af95e11af0dbf8b7da030eb",
}
PORT = "exact_graph_execution.py"
PORT_PIN = "cee1c8e095f139d4e1b839dc84a3c25b96794a96031df05a16f7f876a67391fe"
METHOD = "released-native-vector-polynomial-v1"


def released_ports():
    from empty_bootstrap import PAYLOAD, RELEASE, checked
    import exact_graph_execution as exact
    from leo.analysis import graph_tracklets as graph, polynomial_tracklets as polynomial
    from leo.analysis.localization_v3 import tracks
    from tools.pipeline_eval.variants.experimental import graph_path

    spec = json.loads(checked(PAYLOAD / "spec.json", PINS["spec.json"]))
    for name, pin in PINS.items():
        if name == "spec.json":
            continue
        checked(PAYLOAD / name, pin)
        if spec["sources"].get(name) != pin:
            raise ValueError("The released Graph specification and Graph source pins disagree")
    checked(HERE / PORT, PORT_PIN)
    if (spec["graph_path"]["sha256"] != PINS["graph-path.so"]
            or Path(graph_path.__file__).resolve() != PAYLOAD / NATIVE_MODULE
            or Path(exact.__file__).resolve() != HERE / PORT):
        raise ValueError("The complete Graph entry must use the pinned released implementation")
    # The observation binder already restores these functions for formation.
    # Requiring that boundary avoids wrapping the publication's own Graph audit.
    if tracks.fit_lane is not graph.fit_lane or any(
            getattr(module, name).__code__.co_filename != str(RELEASE / "src" / source)
            for module, name, source in (
                (tracks, "graph_tracks", "leo/analysis/localization_v3/tracks.py"),
                (graph, "_graph", "leo/analysis/graph_tracklets.py"),
                (polynomial, "_best_piece", "leo/analysis/polynomial_tracklets.py"),
            )):
        raise ValueError("Fast edit formation requires the original stock Graph boundary")
    return (PAYLOAD / "graph-path.so", graph_path.native_paths, exact.graph_execution,
            {**PINS, PORT: PORT_PIN, **exact.PINS})


@contextmanager
def enabled(moment):
    """Adapt the existing formation call while retaining its projection and checks."""
    original = moment.formed_features

    def form(native, config, feature, ordinary_graph, report):
        library, native_paths, graph_execution, pins = released_ports()
        scopes = {}

        def prepare(name, operation, packet, approved):
            if name in scopes:
                raise ValueError(f"Repeated Graph preparation for {name}")
            graph = {}
            with native_paths(library, required=True) as paths:
                with graph_execution(enabled=True, audit=graph):
                    result = operation(packet, approved)
            if graph["graph"]["calls"] != 1:
                raise ValueError(f"Expected one released Graph preparation for {name}")
            scopes[name] = dict(graph, native_paths=dict(paths))
            return result

        staged = SimpleNamespace(BIN_HZ=feature.BIN_HZ,
                                 derive=lambda packet, approved: prepare("held_odd_mask", feature.derive, packet, approved))
        result = original(native, config, staged,
                          lambda packet, approved: prepare("ordinary", ordinary_graph, packet, approved), report)
        if set(scopes) != {"held_odd_mask", "ordinary"}:
            raise ValueError("Frozen edit formation must prepare both Graph inputs")
        report["fast_graph_formation"] = dict(method=METHOD, sources=pins, scopes=scopes)
        return result

    with patch.object(moment, "formed_features", form):
        yield
