"""Measure the existing web renderer and attribute its real layer draws."""

import argparse
from collections import Counter
from contextlib import contextmanager
from copy import deepcopy
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from statistics import median
from time import process_time_ns
from unittest.mock import patch

import one_pass_web_png_trial as prior
from one_pass_web_png import render


HERE = Path(__file__).resolve().parent
EXPLICIT = Path("/dev/shm/leo-one-pass-web-png-20261123/physical-v7/result.json")
EXPLICIT_SHA = "223b2331a193dcb7778b1d5b792d14367e20e5916e531c8ad64aa58a92483a2a"
ORDER = ("plain", "profiled", "profiled", "plain", "plain", "profiled",
         "profiled", "plain", "plain", "profiled")
WORK = dict(orbit_figures=2, residual_figures=2, track_figures=1, position_figures=1)


def map_axes(figure):
    rows = []
    for axis in figure.axes:
        legend = axis.get_legend()
        rows.append(dict(
            title=axis.get_title(), xlabel=axis.get_xlabel(), ylabel=axis.get_ylabel(),
            bounds=list(map(float, axis.bbox.bounds)),
            transform=axis.transData.get_affine().get_matrix().tolist(),
            xlim=list(map(float, axis.get_xlim())), ylim=list(map(float, axis.get_ylim())),
            xticks=list(map(float, axis.get_xticks())), yticks=list(map(float, axis.get_yticks())),
            text=[obj.get_text() for obj in axis.texts if obj.get_visible()],
            legend=[obj.get_text() for obj in legend.get_texts()] if legend else [],
            lines=[dict(label=line.get_label(), color=line.get_color(),
                        marker=line.get_marker(), style=line.get_linestyle(),
                        alpha=line.get_alpha(), antialiased=line.get_antialiased(),
                        zorder=line.get_zorder(),
                        points=prior.array_evidence(line.get_xydata()))
                   for line in axis.lines if line.get_visible()],
            collections=[dict(kind=type(c).__name__, points=prior.array_evidence(c.get_offsets()),
                              alpha=c.get_alpha(), zorder=c.get_zorder())
                         for c in axis.collections if c.get_visible()],
        ))
    return rows


@contextmanager
def probes(*, enabled, inventory=False):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng

    original_new = Figure.__init__
    original_draw = FigureCanvasAgg.draw
    original_encode = LosslessPng._encode
    state = dict(outputs=[], construction=0, canvases=0)
    if not enabled:
        yield state
        return

    def construct(figure, *args, **options):
        started = process_time_ns()
        original_new(figure, *args, **options)
        state.update(figure=figure, begin=started, pending_draw=0)
        state["construction"] += 1

    def draw(canvas, *args, **options):
        started = process_time_ns()
        result = original_draw(canvas, *args, **options)
        if canvas.figure is not state.get("figure"):
            raise ValueError("Agg draw had no matching web figure constructor")
        state["pending_draw"] += process_time_ns() - started
        state["canvases"] += 1
        return result

    def encode(encoder, imsave, stream, pixels, options):
        started = process_time_ns()
        result = original_encode(encoder, imsave, stream, pixels, options)
        ended = process_time_ns()
        if not result or type(stream) is not BytesIO:
            raise ValueError("Expected the qualified lossless PNG for every web chart")
        if "begin" not in state:
            raise ValueError("Lossless encoding had no matching web figure")
        item = dict(
            figure_number=state["construction"], draw_cpu_ns=state["pending_draw"],
            encode_cpu_ns=ended - started, interval_cpu_ns=ended - state["begin"],
            size=[int(pixels.shape[1]), int(pixels.shape[0])], stream=stream,
        )
        if inventory and item["size"] == [1680, 960]:
            item["axes"] = map_axes(state["figure"])
        state["outputs"].append(item)
        state.update(begin=ended, pending_draw=0)
        return result

    with (
        patch.object(Figure, "__init__", construct),
        patch.object(FigureCanvasAgg, "draw", draw),
        patch.object(LosslessPng, "_encode", encode),
    ):
        yield state


def name_outputs(streams, pngs, required_figures=(2, 2, 1, 1, 1, 1)):
    seen = set()
    starts = Counter(row["figure_number"] for row in streams)
    if (len(streams) != 8 or sorted(starts.values()) != sorted(required_figures)):
        raise ValueError("Expected two shared orbit bases and four individual figures")
    names = {sha256(raw).hexdigest(): name for name, raw in pngs.items()}
    data = {}
    for row in streams:
        digest = sha256(row["stream"].getvalue()).hexdigest()
        if digest not in names or (name := names[digest]) in seen:
            raise ValueError("Native encoding does not identify one exact publication product")
        seen.add(name)
        data[name] = {k: v for k, v in row.items() if k != "stream"}
    return data


def altered_fixed_zero(packet):
    """Move only the fixed-zero estimate and its display-only RF summary."""
    result = dict(packet, arms=deepcopy(packet["arms"]))
    fixed = result["arms"]["c0"]
    lat, lon = fixed["endpoint_latlon"]
    fixed["endpoint_latlon"] = [lat + .001, lon]
    fixed["residual_rms_hz"] += 7
    return result


def inspect(packet, renderer, options, archived, official, destination):
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    science = prior.verify_packet(packet, official, archived)
    if not all(science.values()):
        raise ValueError(f"Active plotting packet has changed: {science}")
    previous = prior.sealed(EXPLICIT, EXPLICIT_SHA)
    expected = previous["publication"]["direct"]["figures"]
    timings = []
    for mode in ORDER:
        with probes(enabled=mode == "profiled") as state:
            start = prior.clocks()
            pngs, layout = render(renderer, packet, enabled=True, **options)
            timing = prior.since(start)
        if layout != WORK or set(pngs) != set(expected):
            raise ValueError("A current web template fell back or generated incomplete output")
        if any("sha256:" + sha256(raw).hexdigest() != expected[name]["sha256"]
               for name, raw in pngs.items()):
            raise ValueError("Current PNG hashes do not reproduce the reviewed explicit layout")
        charts = name_outputs(state["outputs"], pngs) if mode == "profiled" else {}
        if mode == "profiled" and state["canvases"] != 6:
            raise ValueError("Unexpected render traversal count")
        outside = timing["cpu_ns"] - sum(row["interval_cpu_ns"] for row in charts.values())
        timings.append(dict(mode=mode, timing=timing, charts=charts, outside_cpu_ns=outside))
        print(mode, timing, flush=True)

    with probes(enabled=True, inventory=True) as state:
        pngs, layout = render(renderer, packet, enabled=True, **options)
    charts = name_outputs(state["outputs"], pngs)
    axes = charts["position"]["axes"]
    if len(axes) != 3 or axes[0]["transform"] == axes[1]["transform"]:
        raise ValueError("Expected independent regional search and refinement maps")
    for panel in axes[:2]:
        labels = {row["label"] for row in panel["lines"]}
        if not {"Fitted c selected estimate", "c = 0 selected estimate"}.issubset(labels):
            raise ValueError("Both estimates must be in each map panel")
    changed, work = render(renderer, altered_fixed_zero(packet), enabled=True, **options)
    differs = [name for name in pngs if changed[name] != pngs[name]]
    if layout != WORK or work != WORK or differs != ["position"]:
        raise ValueError(f"Unexpected fixed-zero display dependency: {differs}")
    original_images = {name: prior.image_evidence(raw) for name, raw in pngs.items()}
    if json.loads(json.dumps(original_images)) != expected:
        raise ValueError("PNG sizes, metadata or full RGBA diverge from the reviewed artifacts")
    perturbed = {name: prior.image_evidence(raw) for name, raw in changed.items()}
    if perturbed["position"]["rgba_sha256"] == original_images["position"]["rgba_sha256"]:
        raise ValueError("Fixed-zero perturbation left the decoded map unchanged")

    output = destination / "qualified-explicit"
    output.mkdir()
    store = FastStandardAnalysisStore(output)
    manifest = {k: v for k, v in official["manifest"].items() if k != "artifacts"}
    run = manifest["run_id"]
    store.publish(run, manifest, pngs, position_grid=official["grid"],
                  position_path=official["path"])
    proof = {name: prior.image_evidence(store.artifact(run, name, image["sha256"]))
             for name, image in original_images.items()}
    if proof != original_images:
        raise ValueError("Official artifact readback did not reproduce the full PNGs")
    sidecars = dict(grid=store.position_grid(run), path=store.position_path(run))
    for key, data in sidecars.items():
        reference = official[key]
        expected_binding = dict(reference["binding"],
                                position_png_sha256=proof["position"]["sha256"])
        if data != dict(reference, binding=expected_binding):
            raise ValueError("Original sidecar content or its map binding changed")

    profiled = [row for row in timings if row["mode"] == "profiled"]
    summary = {
        name: {field: median(row["charts"][name][field] for row in profiled)
               for field in ("interval_cpu_ns", "draw_cpu_ns", "encode_cpu_ns")}
        for name in pngs
    }
    return dict(
        arms_owners_path_grid_exact=science, timings=timings, chart_cpu_ns=summary,
        figures=state["construction"], base_agg_draws=state["canvases"],
        fixed_zero_changes=differs, explicit_sha256=EXPLICIT_SHA, map_axes=axes,
        original_pngs=original_images, fixed_zero_perturbed_pngs=perturbed,
        sidecar_sha256={key: canonical_digest(data) for key, data in sidecars.items()},
    )


def run(destination):
    original = prior.authority

    def authority(specification):
        sources = original(specification)
        for path in (Path(__file__), HERE / "calibration-png-layers-protocol.md",
                     EXPLICIT):
            sources["files"][str(path)] = prior.file_sha(path)
        return sources

    with (
        patch.object(prior, "authority", authority),
        patch.object(prior, "ORDER", ORDER),
        patch.object(prior, "compare", inspect),
    ):
        prior.run(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    run(**vars(parser.parse_args()))
