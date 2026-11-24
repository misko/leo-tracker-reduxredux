"""Price already verified exact Agg reuse on one existing dense orbit scene."""

import argparse
from contextlib import nullcontext
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import pickle
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
CAPTURED = Path("/dev/shm/leo-v3-0359-cairo-saved-result01")
CAPTURE_PIN = "a50f7dbd4bef6911e6684794d63eef51d503aa34d5cfd93bc44436caec6aece2"
CAPTURE_SEAL = "68b3c77670a68db94ebb47dc7ae0ae6e2a71c8777267dd5367d3b31d1dba3ac9"
ORDER = ("ordinary", "fixed_restore")
GATE_S = 0.20
PROTOCOL = HERE / "ds30-0359-agg-reuse-protocol.md"


def budget(spans, encodes, full, metric):
    seconds = lambda key: sum(phase[metric] for phase in spans[key])
    construction, draw = (seconds(key) for key in ("make_figure", "base_draw"))
    copying, encoding = seconds("copy") + seconds("restore"), seconds("encode")
    layout = seconds("tight_layout")
    second_band = spans["tight_layout"][1][metric] + spans["subplots"][1][metric]
    result = dict(complete=full[metric], scoped_orbit=spans["whole_orbit"][0][metric], figure_including_layout=construction,
                  base_draw=draw, copies_and_restores=copying, encode=encoding, all_layout=layout,
                  first_restores=sum(row[metric] for row in spans["restore"][::2]) if len(spans["restore"]) == 4 else 0.0,
                  optimistic_second_band_layout_and_buffers=copying + second_band,
                  optimistic_shared_layout_and_buffers=copying + layout + seconds("subplots"))
    if metric == "cpu_s":
        result["encoder_breakdown"] = {key: sum(phase[key] for phase in encodes) for key in (
            "header_cpu_s", "filter_cpu_s", "compress_cpu_s", "write_cpu_s", "encode_cpu_s")}
        result["encoder_cpu_except_deflate"] = encoding - result["encoder_breakdown"]["compress_cpu_s"]
    return result


def replay(lanes, options, libs, *, fixed):
    from empty_bootstrap import clock, now
    from fixed_orbit_artists import fixed_artists
    from leo.presentation import orbit_plot
    from ordinary_orbit_reuse import orbit_draw
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout, shared_orbit_figures as shared

    started = now()
    encodes = []
    encoder = lossless_png.LosslessPng(libs[0], deflate_library=libs[1], profile=encodes)
    artists = None

    def installed(packet, *, require_trial):
        nonlocal artists
        if not require_trial:
            raise ValueError("The pinned ordinary Agg renderer is required")
        with patch.object(orbit_plot, "Figure", raster_layout._OrbitFigure):
            scope = fixed_artists(packet, **options, reuse_pixels=True, raster_layout=raster_layout) if fixed else nullcontext()
            with scope as artists, patch.object(shared, "imsave", encoder.wrap(shared.imsave)):
                return raster_layout.render_shared(packet, **options, reuse_pixels=True)

    images, trace = orbit_draw(installed, lanes, {}, skip=fixed)
    full = clock(started)
    if len(encodes) != 4 or fixed and (artists is None or artists["figures"] != 2 or artists["axes"] != 16):
        raise ValueError("The renderer did not produce all four original encoded views")
    return images, trace | {"encodes": encodes, "fixed_artists": artists, "full": full}


def run(output):
    import empty_bootstrap as boot

    started = boot.now()
    _, spec, _, _, _ = boot.load_runtime()
    from aperture_trial import write
    from dense_geographic_trial import host
    from ds30_0359_cairo_saved import BASE, PRIOR_PIN, SCENE
    from ordinary_orbit_reuse import SOURCES, curve_overlap
    from leo.presentation import orbit_plot
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from PIL import Image
    from tools.pipeline_eval.variants.experimental import raster_layout, shared_orbit_figures

    for module in (orbit_plot, raster_layout, shared_orbit_figures):
        path = Path(module.__file__)
        boot.checked(path, SOURCES[path.name])
    libs, asset_pins = [], {}
    for name in ("png_filter", "png_deflate"):
        library = Path(spec[name]["library"])
        boot.checked(library, spec[name]["sha256"])
        libs.append(library)
        asset_pins[name] = spec[name]
    before = json.loads(boot.checked(BASE / "result.json", PRIOR_PIN))["jobs"]["routed"]["publication"]
    sealed = json.loads(boot.checked(CAPTURED / "prediction-seal.json", CAPTURE_SEAL))
    if sealed[SCENE] != CAPTURE_PIN:
        raise ValueError("The paid candidate did not seal this official live scene")
    lanes, options = pickle.loads(boot.checked(CAPTURED / SCENE, CAPTURE_PIN))
    live = host()
    if live["cpu"] != [2] or live["nice"] < 15 or "prio 7" not in live["ionice"] or set(live["threads"].values()) != {"1"}:
        raise ValueError("The frozen single low-priority Gauss lease is required")
    store = FastStandardAnalysisStore(BASE / "routed/candidate")
    run_id = before["science"]["receipt"]["run_id"]
    setup = boot.clock(started)
    products, traces = {}, {}
    for mode in ORDER:
        products[mode], traces[mode] = replay(lanes, options, libs, fixed=mode == "fixed_restore")
    readback_started = boot.now()
    if traces["ordinary"]["figures"] != traces["fixed_restore"]["figures"]:
        raise ValueError("The two exact Agg compositions changed their artist geometry or labels")
    evidence = {}
    for name in products["ordinary"]:
        expected = before["figures"][name]
        official = store.artifact(run_id, name, expected["sha256"])
        if any(products[mode][name] != official for mode in ORDER):
            raise ValueError(f"The two replays must reproduce the actual ordinary PNG {name}")
        with Image.open(BytesIO(official)) as png:
            rgba = sha256(png.convert("RGBA").tobytes()).hexdigest()
            if rgba != expected["rgba_sha256"] or list(png.size) != expected["size"]:
                raise ValueError("Independent decode changed the published pixels")
            evidence[name] = dict(expected, mode=png.mode, metadata=png.info, bytes=len(official))
    clocks = {mode: {metric: budget(trace["spans"], trace["encodes"], trace["full"], metric)
                     for metric in ("elapsed_s", "cpu_s")} for mode, trace in traces.items()}
    difference = {key: clocks["ordinary"][key]["complete"] - clocks["fixed_restore"][key]["complete"]
                  for key in ("elapsed_s", "cpu_s")}
    source = SOURCES | {name: sha256((HERE / name).read_bytes()).hexdigest() for name in
                        (Path(__file__).name, PROTOCOL.name, "ordinary_orbit_reuse.py", "fixed_orbit_artists.py")}
    write(output, dict(recording="DS30-0359", order=ORDER, machine=live, sources=source, libraries=asset_pins,
          archive_result_sha256=PRIOR_PIN, scene_sha256=CAPTURE_PIN, scene_seal_sha256=CAPTURE_SEAL,
          ordinary_pngs=evidence, stage_clocks=clocks, traces=traces, paired_saving=difference,
          exact_pixels=True, passed_cpu_screen=difference["cpu_s"] >= GATE_S, threshold_s=GATE_S,
          curve_overlap=curve_overlap(lanes), setup=setup, readback=boot.clock(readback_started),
          waveform_reads=0, solver_children=0))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("receipt", type=Path)
    run(cli.parse_args().receipt)
