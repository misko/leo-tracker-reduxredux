"""Compare eight stock and explicit-layout PNGs on the active saved physical fix."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from unittest.mock import patch

from aperture_trial import archive_identity, configuration, read, write
from dense_full_short_crossover import file_sha
from dense_geographic_trial import host
from one_pass_web_png import render
from saved_publication_trial import clocks, image_evidence, sealed, since, verify_packet


HERE = Path(__file__).resolve().parent
SOURCE = Path("/dev/shm/leo-v3-combined-frontier-weak-03")
PINS = {
    "binding.json": "e2e7f912c8aadf4f1c61ec9ea74672546c408f03d6d2570c749e4ee47ffe10c8",
    "candidate/joint-research-receipt.json":
        "61790935d250040d016bcd07955c458949fac402d84bf4760c7cd40683ce4af2",
}
NATIVE = "c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589"
ORDER = ("stock", "direct", "direct", "stock", "stock", "direct",
         "direct", "stock", "stock", "direct")


def authority(specification):
    from leo.presentation import fast_standard_analysis, orbit_plot
    from tools.pipeline_eval.qualification import experimental_publication
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout
    from tools.pipeline_eval.variants.experimental import shared_orbit_figures

    files = (Path(__file__), HERE / "one_pass_web_png.py", HERE / "one-pass-web-png-protocol.md",
             HERE / "full_short_run.py", HERE / "joint_publication.py",
             *(Path(m.__file__) for m in (fast_standard_analysis, orbit_plot,
                 experimental_publication, lossless_png, raster_layout, shared_orbit_figures)))
    if specification["rendering"] != "lossless-raster":
        raise ValueError("Expected the released shared-pixel, layout and lossless renderer")
    return dict(files={str(p): file_sha(p) for p in files}, specification=specification)


def loaded():
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    binding, prior = (sealed(SOURCE / name, digest) for name, digest in PINS.items())
    metadata = prior["receipt"]
    run_id = metadata["run_id"]
    base = SOURCE / "candidate"
    store = FastStandardAnalysisStore(base)
    manifest = read(store.folder(run_id) / "manifest.json")
    native_path, = (base / "fast-scan-automatic-work").glob("*/detections.json")
    native = sealed(native_path, NATIVE)
    terminal = sealed(base / "fast-scan-automatic-work" / run_id / "terminal.json",
                      metadata["terminal_sha256"])
    request = binding["request"]
    observed = dict(manifest=manifest, grid=store.position_grid(run_id),
                    path=store.position_path(run_id), evidence=prior["evidence"])
    if (prior["route"] != "complete" or metadata["decision"] != "complete"
            or terminal["native_sha256"] != canonical_digest(native)
            or request["offered_region"] != metadata["region"]
            or manifest["terminal_sha256"] != metadata["terminal_sha256"]
            or file_sha(Path(request["region_file"])) != request["offer_sha256"]
            or archive_identity(Path(request["archive"]["root"])) != request["archive"]
            or any(canonical_digest(observed[k]) != prior["evidence"][k] for k in ("path", "grid"))):
        raise ValueError("The active saved physical publication changed")
    return binding, prior, observed, native_path


def array_evidence(values):
    import numpy as np

    values = np.ma.asarray(values, dtype=np.float64)
    return (values.shape, sha256(values.filled(np.nan).tobytes()).hexdigest())


def artists(figure, renderer):
    from matplotlib.ticker import FixedLocator

    axes, text, missing = [], [], []
    width, height = figure.bbox.size

    def note(item):
        if item.get_visible() and (label := item.get_text()):
            bbox = item.get_window_extent(renderer)
            text.append(label)
            if bbox.x0 < -1 or bbox.y0 < -1 or bbox.x1 > width + 1 or bbox.y1 > height + 1:
                missing.append((label, tuple(bbox.bounds)))

    for item in figure.texts:
        note(item)
    for legend in figure.legends:
        for item in legend.get_texts():
            note(item)
    for axis in figure.axes:
        for item in (axis.title, axis.xaxis.label, axis.yaxis.label, *axis.texts):
            note(item)
        if type(axis.xaxis.get_major_locator()) is FixedLocator:
            for item in axis.get_xticklabels():
                note(item)
        if legend := axis.get_legend():
            for item in legend.get_texts():
                note(item)
        lines = tuple((array_evidence(line.get_xydata()), line.get_color(),
                       line.get_linestyle(), line.get_marker()) for line in axis.lines
                      if line.get_visible())
        collections = tuple((type(c).__name__, array_evidence(c.get_offsets()),
                             None if c.get_array() is None else array_evidence(c.get_array()),
                             array_evidence(c.get_facecolors())) for c in axis.collections
                            if c.get_visible())
        bars = tuple((p.get_x(), p.get_y(), p.get_width(), p.get_height(), p.get_facecolor())
                     for p in axis.patches if p.get_visible() and hasattr(p, "get_x"))
        axes.append(dict(xlim=tuple(axis.get_xlim()), ylim=tuple(axis.get_ylim()),
                         lines=lines, collections=collections, bars=bars))
        if axis.xaxis.label.get_visible() and axis.get_xlabel():
            label_box = axis.xaxis.label.get_window_extent(renderer)
            if any(label_box.overlaps(legend.get_window_extent(renderer)) for legend in figure.legends):
                missing.append(("x-axis label overlaps figure legend", tuple(label_box.bounds)))
        if axis.title.get_visible() and axis.get_title():
            title_box = axis.title.get_window_extent(renderer)
            if any(title_box.overlaps(other.bbox) for other in figure.axes
                   if other.get_label() == "<colorbar>"):
                missing.append(("axis title overlaps colorbar", tuple(title_box.bounds)))
    return dict(text=text, axes=axes), missing


@contextmanager
def observe_artists():
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng

    original_draw, original_encode = FigureCanvasAgg.draw, LosslessPng._encode
    current, rows = None, []

    def draw(canvas, *args, **options):
        nonlocal current
        operation = original_draw(canvas, *args, **options)
        current = canvas
        return operation

    def encode(*args, **options):
        if current is None:
            raise ValueError("PNG encoder did not follow an Agg draw")
        rows.append(artists(current.figure, current.get_renderer()))
        return original_encode(*args, **options)

    with patch.object(FigureCanvasAgg, "draw", draw), patch.object(LosslessPng, "_encode", encode):
        yield rows


def compare(packet, renderer, options, prior, observed, destination):
    from leo.application.localization_v3_engine import _json_value
    from leo.contracts.digests import canonical_digest
    from leo.contracts.fast_standard_analysis import PLOTS
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    numerical = verify_packet(packet, observed, prior)
    if not all(numerical.values()):
        raise ValueError(f"Active physical plotting packet does not reproduce: {numerical}")
    expected = observed["evidence"]["images"]
    runs, product_digests, product_images = [], {}, {}
    for mode in ORDER:
        before = clocks()
        images, work = render(renderer, packet, enabled=mode == "direct", **options)
        timing = since(before)
        pins = {name: "sha256:" + sha256(data).hexdigest() for name, data in images.items()}
        if pins != product_digests.setdefault(mode, pins) or images.keys() != set(PLOTS):
            raise ValueError("The eight rendered artifacts are incomplete or nondeterministic")
        if mode == "stock" and any(pins[name] != expected[name]["sha256"] for name in images):
            raise ValueError("The normal renderer did not reproduce archived PNG bytes")
        if mode == "direct" and work != dict(orbit_figures=2, residual_figures=2,
                                             track_figures=1, position_figures=1):
            raise ValueError(f"The explicit templates did not render every figure: {work}")
        product_images.setdefault(mode, images)
        runs.append(dict(mode=mode, work=work, render=timing, bytes=sum(map(len, images.values()))))
        print(mode, timing, flush=True)

    semantic = {}
    for mode, images in product_images.items():
        with observe_artists() as artwork:
            audited, _ = render(renderer, packet, enabled=mode == "direct", **options)
        if images != audited or len(artwork) != len(PLOTS):
            raise ValueError("The untimed artist audit must see the measured products")
        semantic[mode] = artwork
    stock, direct = (semantic[mode] for mode in ("stock", "direct"))
    if [a[0] for a in stock] != [a[0] for a in direct]:
        raise ValueError("Labels, limits, curves, point arrays or bars changed")
    expected_bad = [set(x[0] for x in a[1]) for a in stock]
    if any(set(x[0] for x in a[1]) - old for a, old in zip(direct, expected_bad, strict=True)):
        raise ValueError(f"Explicit layout clipped new text: {[a[1] for a in direct]}")
    evidence = dict(
        numerical=numerical,
        runs=runs,
        artists_sha256=canonical_digest(json.loads(json.dumps([a[0] for a in stock], default=_json_value))),
        artist_text=[a[0]["text"] for a in stock],
        clipping={mode: [a[1] for a in artwork] for mode, artwork in semantic.items()},
    )
    write(destination / "render-observation.json", evidence)

    publication = {}
    original = observed["manifest"]
    run = original["run_id"]
    for mode, images in product_images.items():
        output = destination / mode
        output.mkdir()
        current = FastStandardAnalysisStore(output)
        manifest = {k: v for k, v in original.items() if k != "artifacts"}
        current.publish(run, manifest, images, position_grid=observed["grid"],
                        position_path=observed["path"])
        official = read(current.folder(run) / "manifest.json")
        figures = {n: image_evidence(current.artifact(run, n, product_digests[mode][n])) for n in PLOTS}
        refreshed = {"grid": current.position_grid(run), "path": current.position_path(run)}
        same = {key: actual == dict(observed[key], binding=dict(
            observed[key]["binding"], position_png_sha256=product_digests[mode]["position"]))
            for key, actual in refreshed.items()}
        exact = {k: v for k, v in official.items() if k != "artifacts"} == manifest and all(same.values())
        if not exact or any(p["size"] != expected[n]["size"] for n, p in figures.items()):
            raise ValueError("The official publisher changed chart dimensions or numerical bindings")
        publication[mode] = dict(figures=figures, sidecars_exact_except_position_png=same)
    for name in PLOTS:
        first, second = (publication[mode]["figures"][name] for mode in ("stock", "direct"))
        if any(first[k] != second[k] for k in ("size", "mode", "metadata")):
            raise ValueError("PNG mode, DPI, image size or metadata changed")
    ratios = []
    for a, b in zip(runs[::2], runs[1::2], strict=True):
        original, candidate = (a, b) if a["mode"] == "stock" else (b, a)
        ratios.append({k: candidate["render"][k] / original["render"][k] for k in a["render"]})
    return dict(evidence, publication=publication, paired_ratios=ratios,
                median_ratios={k: median(r[k] for r in ratios) for k in ratios[0]})


def run(destination):
    publication, specification = configuration()
    import full_short_run
    import joint_publication
    from regional_probe_block_binding import guarded_projection
    from tools import algo08_scan

    machine = host()
    binding, prior, observed, native_path = loaded()
    candidate = binding["commands"]["candidate"]
    read_flag = lambda name: candidate[candidate.index("--" + name) + 1]
    request = binding["request"]
    saved_digest = prior["evidence"]["native_sha256"] if "native_sha256" in prior["evidence"] else (
        "sha256:" + NATIVE)
    single, stock, block = map(Path, (read_flag("geographic-library"),
        read_flag("regional-track-library"), read_flag("frontier-block-library")))
    flags = [
        "--recording", request["recording"], "--archive", request["archive"]["root"],
        "--region", request["region_file"], "--saved", str(native_path), "--saved-digest", saved_digest,
        "--geographic-library", str(single), "--regional-track-library", str(stock),
        "--track-graph", "installed", "--reuse-cold-track-rows", "--reuse-grid-phase-states",
        "--skip-empty-proof", "--output", str(destination / "replay"),
    ]
    destination.mkdir()
    lock = dict(authority=authority(specification), originals=PINS, native=NATIVE, order=ORDER,
                host=machine, request=request, libraries={str(p): file_sha(p) for p in (single, stock, block)},
                flags=flags)
    write(destination / "source-lock.json", lock)
    original, projection = algo08_scan.analyze, full_short_run.geographic_projection
    outcome = {}

    def intercept(*args, **kwargs):
        renderer = algo08_scan.render

        def measured(packet, **options):
            outcome.update(compare(packet, renderer, options, prior, observed, destination))
            return renderer(packet, **options)

        with patch.object(algo08_scan, "render", measured):
            return original(*args, **kwargs)

    def project(g, t):
        return guarded_projection(g, t, block, projection)

    with (patch.object(algo08_scan, "analyze", intercept),
          patch.object(joint_publication, "configuration", return_value=(publication, specification)),
          patch.object(full_short_run, "geographic_projection", project)):
        full_short_run.main(flags)
    if not outcome:
        raise ValueError("The normal publication did not render the active saved fix")
    write(destination / "result.json", dict(source_sha256=file_sha(destination / "source-lock.json"), **outcome))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    run(**vars(parser.parse_args()))
