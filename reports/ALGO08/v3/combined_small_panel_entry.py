"""Opt in at the published field batch's authenticated handoff and grid ports."""

import argparse
import json
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager, nullcontext
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from time import perf_counter_ns, process_time_ns
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
GRID = Path("/tmp/leo-profiled-grid-export-capsule-02/profiled.so")
GRID_PIN = "8f65bd73d24ff04f6fded7ac414e06fb5dc08600d3a5c61f86203bb6dceff03f"
GRAPH_PIN = "2ecadcd736ea59184333280626e8c48de7afa2aed4ad95974bd1c5a564895c35"
FEATURE_PIN = "65a9934437d2d495b269f7377dd4d82ebe4d4e1e6f6b8e3e89717f89a25e8843"
TRACK_PIN = "a7a252b2fd9a9fe7c617f4565b171c159846705803f4fb80ab755ba9ea94710a"
EXPORT_PIN = "9b62914ac659619e8883e8ab3f45e41114452e1c0363d9e5ad9d8455348d829c"
STOCK_GRID_SOURCE = "aa5d7ab17ce82e4bd64e463de0fddf710275634cf48675cf6076eeba6c184831"
STOCK_GRID_BINARY = "5a6e5627844a07a3bf2291b248520949f8b10e41d0421b6d6dc0da2b19d430b5"
SCHEDULE = ["full", *(["short_primary"] * 7)]


def module(boot, name, pin):
    path = HERE / (name + ".py")
    boot.checked(path, pin)
    spec = spec_from_file_location("_combined_small_panel_" + name, path)
    loaded = module_from_spec(spec)
    sys.modules[spec.name] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def load_ports(boot, *, ordinary_grid=False):
    from leo.analysis import graph_tracklets, polynomial_tracklets
    from leo.analysis.localization_v3 import tracks
    from leo.application import localization_v3 as app
    from leo.contracts.digests import canonical_digest

    feature = module(boot, "held_cfo_features", FEATURE_PIN)
    if ordinary_grid:
        from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

        expected = boot.PAYLOAD / "tools/pipeline_eval/variants/algo08_posterior_handoff.py"
        boot.checked(expected, STOCK_GRID_SOURCE)
        boot.checked(boot.PAYLOAD / "posterior-grid-handoff.so", STOCK_GRID_BINARY)
        if any(
            Path(op.__code__.co_filename) != expected
            for op in (handoff.grid_handoff, handoff.Capture.run)
        ):
            raise ValueError("Require the installed unmodified numerical grid function")
        grid = SimpleNamespace(handoff=handoff)
    else:
        grid = module(boot, "profiled_grid_export", EXPORT_PIN)
    if (
        Path(app.__file__).resolve() != boot.RELEASE / "src/leo/application/localization_v3.py"
        or app.prepare_tracks is not tracks.prepare_tracks
        or feature.prepare_tracks is not tracks.prepare_tracks
        or Path(grid.handoff.__file__).resolve()
        != boot.PAYLOAD / "tools/pipeline_eval/variants/algo08_posterior_handoff.py"
    ):
        raise ValueError("The reviewed installed Graph or grid port is unavailable")
    config = polynomial_tracklets.TrackConfig(
        **json.loads(boot.checked(boot.RELEASE / "assets/tracks.json", TRACK_PIN))["config"]
    )
    stock = [
        (component, name, getattr(component, name))
        for component, name in (
            (tracks, "graph_tracks"),
            (tracks, "fit_lane"),
            (graph_tracklets, "_graph"),
            (polynomial_tracklets, "_best_piece"),
        )
    ]
    graph_path = HERE / "masked_cfo_saved.py"
    # Bind only the published observation port. The saved replay launcher and
    # its historical input lookup never enter this raw worker.
    functions = dict(
        contextmanager=contextmanager,
        ExitStack=ExitStack,
        patch=patch,
        signed=SimpleNamespace(canonical=canonical_digest),
        perf_counter_ns=perf_counter_ns,
        process_time_ns=process_time_ns,
    )
    boot.load_definitions(
        boot.checked(graph_path, GRAPH_PIN),
        str(graph_path),
        ("GraphReadback", "clock", "elapsed", "overlay_rows", "bind_graph"),
        functions,
    )
    if not ordinary_grid:
        grid.checked_symbol(GRID, GRID_PIN, "nb_profiled_posterior")
    return SimpleNamespace(
        boot=boot,
        app=app,
        tracks=tracks,
        feature=feature,
        grid=grid,
        config=config,
        stock=stock,
        bind=functions["bind_graph"],
        canonical=canonical_digest,
    )


def publication(boot, ordinary, audit, *, ordinary_grid=False):
    def publish(args, publisher, specification, handoff, *options, **kwargs):
        if audit["publication_calls"]:
            raise ValueError("The opt-in must bind to one original authenticated handoff")
        started = boot.now()
        ports = load_ports(boot, ordinary_grid=True) if ordinary_grid else load_ports(boot)
        audit["port_setup"] = boot.clock(started)
        pin = specification["posterior_grid_handoff"]["sha256"]
        expected = STOCK_GRID_BINARY if ordinary_grid else ports.grid.STOCK_POSTERIOR_SHA256
        if pin != expected:
            raise ValueError("Require the exact released posterior export")
        audit["publication_calls"] += 1
        graph, grid = audit["cfo"], Counter()
        audit["handoff_sha256"] = ports.canonical(handoff.native)
        if ordinary_grid:
            handoff_module = ports.grid.handoff
            before = handoff_module.grid_handoff, handoff_module.Capture.run
            grid_scope = nullcontext()
        else:
            grid_scope = ports.grid.profiled_grid(GRID, GRID_PIN, grid, proof=True)
        with (
            ports.bind(
                ports.app,
                ports.tracks,
                ports.feature,
                ports.config,
                handoff.native,
                graph,
                stock_ports=ports.stock,
            ),
            grid_scope,
        ):
            result = ordinary(args, publisher, specification, handoff, *options, **kwargs)
        audit["grid"] = dict(grid)
        if ordinary_grid:
            if before != (handoff_module.grid_handoff, handoff_module.Capture.run):
                raise ValueError("The ordinary grid port changed during publication")
            audit["ordinary_grid"] = dict(source_sha256=STOCK_GRID_SOURCE, binary_sha256=expected)
        return result

    return publish


def finish(output, receipt, audit, batch, *, ordinary_grid=False):
    original = json.loads((output / "unified-short-bootstrap.json").read_bytes())
    recipe = original["held_anchor_route"]["receiver_recipe"]
    if recipe["rule"] != SCHEDULE or recipe["streams"] != ["edge", "channel", "actual_rf_hz"]:
        raise ValueError("The opt-in must use the exact sparse 20/8 receiver")
    graph, grid = audit["cfo"], audit["grid"]
    if audit["publication_calls"] and audit["handoff_sha256"] != original["native_sha256"]:
        raise ValueError("The opt-in did not consume the published original native handoff")
    if (
        receipt["decision"] == "complete"
        and (
            audit["publication_calls"] != 1
            or graph.get("feature_calls") != 1
            or not graph.get("attempts")
            or not (audit.get("ordinary_grid") if ordinary_grid else grid.get("attempted"))
        )
        or receipt["decision"] == "withheld"
        and grid.get("attempted")
        or grid.get("unsupported_library")
        or grid.get("proof_stock_refused")
    ):
        raise ValueError("The enabled scientific ports did not complete their expected route")
    audit.update(
        native_sha256=original["native_sha256"],
        decision=receipt["decision"],
        sources=dict(
            graph=GRAPH_PIN,
            feature=FEATURE_PIN,
            config=TRACK_PIN,
            exporter=STOCK_GRID_SOURCE if ordinary_grid else EXPORT_PIN,
            grid=STOCK_GRID_BINARY if ordinary_grid else GRID_PIN,
        ),
    )
    batch.write(output / "combined-small-panel-witness.json", audit)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("runtime", type=Path)
    cli.add_argument("--probe-ports", action="store_true")
    cli.add_argument("--ordinary-grid", action="store_true")
    cli.add_argument("batch_arguments", nargs=argparse.REMAINDER)
    # Keep every argument after the selected frozen tree in the real batch parser.
    args = cli.parse_args()
    if args.runtime != args.runtime.resolve(strict=True):
        raise ValueError("Require an independently prepared frozen runtime")
    code = args.runtime / "reports/ALGO08/v3"
    sys.path[:0] = [str(code), str(args.runtime)]
    import empty_bootstrap as boot
    import integrated_original_batch as batch

    if args.probe_ports:
        boot.load_runtime()
        ports = load_ports(boot, ordinary_grid=args.ordinary_grid)
        from combined_frontier_run import load_prefetch

        from reports.ALGO08.v3.prefetch_snapshots import binding

        if not callable(load_prefetch()) or not callable(binding) or not callable(ports.bind):
            raise ValueError("The exact original scientific ports failed to load")
        print(json.dumps(dict(ports=True, waveform_reads=0, graph_calls=0, solves=0)))
        return

    run = batch.run

    def active(config, *call):
        import exact_named_raw as raw

        audit = dict(publication_calls=0, cfo={}, grid={})
        ordinary = raw.publish_active
        # Keep early scientific imports out of the receiver. The charted
        # publisher captures this callback before raw acquisition starts.
        with patch.object(
            raw,
            "publish_active",
            publication(boot, ordinary, audit, ordinary_grid=args.ordinary_grid),
        ):
            receipt = run(config, *call)
        if raw.publish_active is not ordinary:
            raise ValueError("A scientific opt-in escaped the raw batch lifetime")
        finish(config.bulk_root, receipt, audit, batch, ordinary_grid=args.ordinary_grid)
        return receipt

    arguments = args.batch_arguments
    if arguments[0:1] == ["--"]:
        arguments = arguments[1:]
    with patch.object(batch, "run", active):
        batch.main(["--reuse-prefetched-snapshots", *arguments])


if __name__ == "__main__":
    main()
