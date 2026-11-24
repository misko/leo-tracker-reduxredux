"""Price the existing positive imports and final Agg charts without a solve."""

import argparse
from collections import defaultdict
from contextlib import contextmanager
from functools import partial
from gzip import decompress
from hashlib import sha256
import json
import os
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
CONTROL = HERE/"measurements/combined-successor-cairo.json.gz"
CONTROL_SHA = "ab222fbb9fec094e54e7c74f15b61a60c727a69aa741f2adca2f7668b7af3ec1"
SCENE = Path("/dev/shm/leo-v3-combined-frame-portable-result02/candidate/render-scene.pickle")
SCENE_SHA = "e222976de38b98d0147cc6abcf21d90693483b6b3e3154c5c211da0c8ba62361"
PRESENTATION_ROOTS = (
    "matplotlib", "leo.presentation.orbit_plot", "leo.presentation.fast_scan_orbits",
    "leo.presentation.fast_standard_analysis", "leo.presentation.regional_position",
    "tools.pipeline_eval.variants.experimental.raster_layout",
    "tools.pipeline_eval.variants.experimental.shared_orbit_figures",
    "tools.pipeline_eval.variants.experimental.lossless_png",
)


class PrefixReached(Exception):
    pass


def deny_inputs(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        path = Path(os.path.abspath(os.fsdecode(args[0])))
        if path.is_relative_to("/srv/bulk") or path.is_relative_to("/mnt/qnap01") or path.name.endswith((".ci16", ".ci16.zst", ".tle")):
            raise ValueError("This publication census is limited to the sealed plot scene and code")


def ownership(rows, roots):
    """Sum exclusive clocks once, even when a whole root nests a second root."""
    inherited, exclusive, branch = {}, defaultdict(int), defaultdict(int)
    for row in rows:
        name = row["name"]
        owns = any(name == key or name.startswith(key + ".") for key in roots)
        inherited[row["index"]] = owns or inherited.get(row["parent"], False)
        if owns:
            for key in ("cpu_ns", "elapsed_ns"):
                exclusive[key] += row["exclusive_"+key]
        if inherited[row["index"]]:
            for key in ("cpu_ns", "elapsed_ns"):
                branch[key] += row["exclusive_"+key]
    return dict(exclusive=dict(exclusive), inclusive_union=dict(branch))


def active_prefix(trace, subject):
    import empty_bootstrap as boot
    from combined_frontier_run import load_prefetch
    from combined_successor_raw_entry import solver_ports
    import exact_named_raw as raw
    from legacy_first_map_entry import parser

    trace.phase = "receiver_startup"
    _, spec, sources, publication, _ = boot.load_runtime()
    boot.staged_scanner(sources)
    boot.receiver_symbols(sources)
    load_prefetch()
    from short_graph_guard import prove
    from eight_ms_native_receiver import prepare

    if not callable(prove) or not callable(prepare) or set(boot.SCIENTIFIC_IMPORTS) & sys.modules.keys():
        raise ValueError("Expected the original receiver-first prefix with no scientific modules")
    trace.phase = "active_prefix"
    args = parser().parse_args(subject["admitted"]["command"][6:])
    if not args.cairo_six_sheets:
        raise ValueError("Expected the measured switched positive renderer")

    def request(*args):
        raise PrefixReached

    audit = {}
    try:
        with patch.object(raw, "request_from_handoff", request), solver_ports(subject["admitted"]["artifacts"], audit):
            raw.publish_active(args, publication, spec, SimpleNamespace(receiver=None))
    except PrefixReached:
        if "matplotlib" not in sys.modules or "grid" not in audit:
            raise ValueError("The active setup failed to bind its real imports")
    else:
        raise ValueError("Expected the positive callback to stop before the numerical request")
    return spec


def render(trace, spec, subject):
    from active_imports import clocks, elapsed
    from direct_orbit_entry import native_orbits
    import direct_orbit_entry
    import direct_residual_figures as residual
    from empty_bootstrap import checked
    from history_cairo_render import binding
    from leo.presentation import fast_standard_analysis as plots
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout

    trace.phase = "scene_load"
    packet, options = pickle.loads(checked(SCENE, SCENE_SHA))
    title = subject["witness"]["ports"]["cairo_layout"]["original_recording_title"]
    apps = subject["witness"]["evidence"]["detail"]["arms"]
    if packet["arms"] != apps or options["evaluation_reference"] is not None:
        raise ValueError("The saved plot packet differs from the current observation owners")
    title_options = options | {"title": title}
    trace.phase = "render_setup"
    libraries = []
    for key in ("png_filter", "png_deflate"):
        pin = spec[key]
        path = Path(pin["library"])
        checked(path, pin["sha256"])
        libraries.append(path)
    encoder = lossless_png.LosslessPng(libraries[0], deflate_library=libraries[1])
    output = SimpleNamespace(render=partial(lossless_png.render_lossless_png, encoder=encoder))
    audit, timings, encodes = {}, defaultdict(list), []
    last_encode = None

    def timed(name, operation):
        def measured(*args, **kwargs):
            started = clocks()
            result = operation(*args, **kwargs)
            timings[name].append(elapsed(started))
            return result
        return measured

    original_encode, original_position = encoder._encode, plots.render_position

    def encode(*args, **kwargs):
        nonlocal last_encode
        started = clocks()
        result = original_encode(*args, **kwargs)
        if not result:
            raise ValueError("Expected the unmodified reviewed PNG encoder")
        encodes.append(elapsed(started))
        last_encode = clocks()
        return result

    def position(*args, **kwargs):
        if len(encodes) != 7:
            raise ValueError("The track-RMS PNG did not precede the position map")
        return timed("position", original_position)(*args, **kwargs)

    @contextmanager
    def orbits(installed, counts):
        with native_orbits(installed, counts):
            original = raster_layout.render_shared
            with patch.object(raster_layout, "render_shared", timed("orbits", original)):
                yield

    def raster(*args, **kwargs):
        result = timed("residual_paint", residual_raster)(*args, **kwargs)
        return result

    residual_raster = residual.raster
    track_begin = clocks()

    def timed_encode(*args, **kwargs):
        nonlocal track_begin
        result = encode(*args, **kwargs)
        if len(encodes) == 6:
            track_begin = last_encode
        elif len(encodes) == 7:
            timings["track-rms"].append(elapsed(track_begin))
        return result

    trace.phase = "render"
    with (patch.object(encoder, "_encode", timed_encode),
          patch.object(plots, "render_position", position),
          patch.object(direct_orbit_entry, "native_orbits", orbits),
          patch.object(residual, "raster", raster),
          patch.object(residual, "scene", timed("residual_scene", residual.scene)),
          binding(output, audit, orbit_sheets=True)):
        images = timed("all", output.render)(packet, **title_options)
    wanted = {name: item["sha256"] for name, item in subject["science"]["images"].items()}
    hashes = {name: "sha256:"+sha256(image).hexdigest() for name, image in images.items()}
    if hashes != wanted or len(encodes) != 8 or len(timings["orbits"]) != 1 or len(timings["position"]) != 1:
        raise ValueError(f"The render replay must reproduce the eight current Cairo images: {[name for name in wanted if hashes.get(name) != wanted[name]]}")
    return dict(timings=timings, encodes=encodes, audit=audit, png_hashes=hashes, frozen_title=title)


def budget(modules, layers, target):
    import_work = ownership([row for row in modules if row["phase"] != "render"], PRESENTATION_ROOTS)
    mpl_work = ownership([row for row in modules if row["phase"] != "render"], ("matplotlib",))
    result = {}
    spans, encodes = layers["timings"], layers["encodes"]
    for metric in ("cpu_ns", "elapsed_ns"):
        value = lambda stage: sum(row[metric] for row in spans[stage])
        # The native orbit timer already includes its own four encodes.
        obligatory = (value("orbits") + value("residual_paint") + value("residual_scene")
                      + sum(row[metric] for row in encodes[4:8]))
        charts = value("position") + value("track-rms") - sum(row[metric] for row in encodes[6:])
        removable_upper = max(0, value("all") - obligatory)
        prefix_upper = import_work["inclusive_union"].get(metric, 0)
        result[metric] = dict(all_figure_ns=value("all"), retained_native_and_encode_ns=obligatory,
                              final_two_net_of_encode_ns=charts, other_figure_headroom_ns=removable_upper-charts,
                              gross_removable_ns=prefix_upper+removable_upper,
                              remaining_target_ns=round(target*1e9),
                              optimism_margin_ns=prefix_upper+removable_upper-round(target*1e9))
    return dict(pre_render_presentation=import_work, pre_render_matplotlib=mpl_work, ceilings=result)


def run(path):
    from active_imports import ImportTrace
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import checked

    sys.addaudithook(deny_inputs)
    machine = host()
    if path.exists() or path.parent != Path("/dev/shm"):
        raise ValueError("Use a fresh small tmpfs receipt")
    subject = json.loads(decompress(checked(CONTROL, CONTROL_SHA)))["subject"]
    target = subject["modeled_cohort_gates"]["elapsed_s"]
    deficit = target["indexed_s"] - target["baseline_s"]/1.6
    trace = ImportTrace()
    with trace.scope():
        spec = active_prefix(trace, subject)
        layers = render(trace, spec, subject)
    write(path, dict(published=CONTROL_SHA, scene=SCENE_SHA, machine=machine, layer_scope=layers,
                     budget=budget(trace.modules, layers, deficit), imports=trace.modules,
                     source_sha256={p.name: sha256(p.read_bytes()).hexdigest() for p in
                                    (Path(__file__), HERE/"matplotlib-free-publication-protocol.md")},
                     waveform_reads=0, solver_runs=0, renderer_runs=1))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("receipt", type=Path)
    run(cli.parse_args().receipt)
