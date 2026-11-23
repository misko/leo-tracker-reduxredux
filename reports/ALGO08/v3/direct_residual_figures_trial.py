"""Measure direct residual drawing inside one complete authenticated saved render."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
NAMES = ("ch1-4-residuals", "ch5-8-residuals")


def stock_scene(figure):
    return dict(heading=tuple(figure._suptitle.get_text().split("\n")), axes=[
        dict(title=ax.get_title(), xlabel=ax.get_xlabel(), ylabel=ax.get_ylabel(),
             xlim=ax.get_xlim(), ylim=ax.get_ylim(),
             zero=tuple(ax.lines[0].get_ydata()),
             series=[(p.get_facecolors()[0].copy(), p.get_offsets().copy(), p.get_sizes().tolist(),
                      p.get_linewidths().tolist()) for p in ax.collections],
             ticks=[[(float(v), item.get_text()) for v, item in zip(locations, labels, strict=True)
                     if limits[0] <= v <= limits[1]]
                    for locations, labels, limits in (
                        (ax.get_xticks(), ax.get_xticklabels(), ax.get_xlim()),
                        (ax.get_yticks(), ax.get_yticklabels(), ax.get_ylim()),
                    )])
        for ax in figure.axes
    ])


def compare_scene(reference, direct, ticks):
    import numpy as np

    if reference["heading"] != direct["heading"] or len(reference["axes"]) != len(direct["axes"]):
        raise ValueError("Direct residual sheet changed its original heading or axis count")
    difference = pairs = points = 0
    marker_sizes, marker_strokes = set(), set()
    for expected, actual, positions in zip(reference["axes"], direct["axes"], ticks, strict=True):
        if (any(expected[key] != actual[key] for key in ("title", "xlabel", "ylabel", "xlim", "ylim"))
                or expected["zero"] != (0, 0)):
            raise ValueError(f"Residual label, limit or zero line changed for {actual['title']}")
        for (palette, coordinates), (color, stock, sizes, strokes) in zip(actual["series"], expected["series"], strict=True):
            if (not np.array_equal(coordinates, stock)
                    or not np.array_equal([v / 255. for v in bytes.fromhex(palette)] + [1.], color)):
                raise ValueError("Direct residual scatter changed coordinates, color or order")
            marker_sizes.update(sizes)
            marker_strokes.update(strokes)
            points += len(stock)
        pairs += 2
        difference += sum(list(candidate) != stock
                          for stock, candidate in zip(expected["ticks"], positions, strict=True))
    return dict(scatter_points=points, axis_tick_sets=pairs, changed_tick_sets=difference,
                stock_marker_sizes=sorted(marker_sizes), stock_marker_strokes=sorted(marker_strokes))


def pixels(stock, candidate):
    import numpy as np
    from PIL import Image

    def decode(data):
        with Image.open(BytesIO(data)) as value:
            value.load()
            return dict(size=value.size, info=value.info, mode=value.mode), np.asarray(value.convert("RGBA"))

    start = process_time_ns()
    a, p = decode(stock)
    b, q = decode(candidate)
    if a != b or a["mode"] != "RGBA":
        raise ValueError(f"Native residual output changed original image metadata: {a!r} / {b!r}")
    result = dict(metadata=b, stock_rgba_sha256=sha256(p.tobytes()).hexdigest(),
                  candidate_rgba_sha256=sha256(q.tobytes()).hexdigest())
    result["decode_and_hash_cpu_ns"] = process_time_ns() - start
    delta = np.abs(p.astype(np.int16)-q.astype(np.int16))
    result.update(changed_pixel_fraction=float(np.any(delta, axis=2).mean()),
                  mean_absolute_rgb_error=float(delta[..., :3].mean()),
                  encoded_bytes=dict(stock=len(stock), direct=len(candidate)))
    return result


def draw(renderer, packet, options, proof, scratch):
    from calibration_png_layers import name_outputs, probes
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng

    axes, codec, inventory_ns = [], [], []
    original_draw, original_encode = FigureCanvasAgg.draw, LosslessPng._encode

    def inventory(canvas, *args, **kwargs):
        result = original_draw(canvas, *args, **kwargs)
        if tuple(canvas.figure.get_size_inches()) == (15, 11):
            start = process_time_ns()
            axes.append(stock_scene(canvas.figure))
            inventory_ns.append(process_time_ns()-start)
        return result

    def encoder(instance, imsave, stream, rgba, metadata):
        if rgba.shape == (1375, 1875, 4):
            codec.append((instance, imsave, dict(metadata)))
        return original_encode(instance, imsave, stream, rgba, metadata)

    start = process_time_ns()
    with patch.object(FigureCanvasAgg, "draw", inventory), patch.object(LosslessPng, "_encode", encoder):
        with probes(enabled=True) as work:
            original = renderer(packet, **options)
    stock_ns = process_time_ns()-start - sum(inventory_ns)
    observed = name_outputs(work["outputs"], original)
    if len(axes) != len(codec) or len(axes) != 2:
        raise ValueError("The standard renderer omitted a residual reference")
    for name, overhead in zip(NAMES, inventory_ns, strict=True):
        for key in ("interval_cpu_ns", "draw_cpu_ns"):
            observed[name][key] -= overhead

    start = process_time_ns()
    from direct_residual_figures import cairo_library, raster, scene

    library = cairo_library()
    load_ns = process_time_ns()-start
    start = process_time_ns()
    charts = scene(packet, options["title"])
    scene_ns = process_time_ns()-start
    outputs, results = dict(original), {}
    for name, expected, (encode, imsave, metadata) in zip(NAMES, axes, codec, strict=True):
        start = process_time_ns()
        rgba, ticks = raster(charts[name], library)
        raster_ns = process_time_ns()-start
        start = process_time_ns()
        payload = BytesIO()
        if not encode._encode(imsave, payload, memoryview(rgba), metadata):
            raise ValueError("The permitted PNG codec rejected native RGBA")
        encode_ns = process_time_ns()-start
        outputs[name] = payload.getvalue()
        results[name] = dict(raster_cpu_ns=raster_ns, encode_cpu_ns=encode_ns,
                             science=compare_scene(expected, charts[name], ticks),
                             media=pixels(original[name], outputs[name]))
        (scratch / f"stock-{name}.png").write_bytes(original[name])
        (scratch / f"direct-{name}.png").write_bytes(outputs[name])
    proof.update(stock_total_cpu_ns=stock_ns, stock_intervals=observed, candidate_setup_cpu_ns=load_ns,
                 candidate_scene_cpu_ns=scene_ns, candidate=results, reference_inventory_cpu_ns=sum(inventory_ns),
                 stock_hashes={name: sha256(data).hexdigest() for name, data in original.items()})
    return outputs


def worker(job, output):
    from aperture_trial import write
    from cumulative_grid_projection import worker as publish
    import unified_short_bootstrap as entry

    original = entry.layout_renderer
    proof = {}

    @contextmanager
    def layout(scan, enabled, audit):
        with original(scan, enabled, audit):
            renderer = scan.render

            def experimental(packet, **options):
                return draw(renderer, packet, options, proof, output.parent)

            with patch.object(scan, "render", experimental):
                yield

    with patch.object(entry, "layout_renderer", layout):
        publish(job, "installed", output)
    write(output / "direct-residual-audit.json", proof)


def run(root):
    from aperture_trial import RELEASE, archive_identity, read, write
    from combined_frontier_run import BLOCK_SHA
    from cumulative_grid_projection import enrolled
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from short_raw_diagnostic import measure, pairs

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("The measured publication requires a fresh tmpfs parent")
    request, packet, expected = enrolled("weak")
    data = checked(packet, request["native"].removeprefix("sha256:"))
    raw = json.loads(data)
    if archive_identity(Path(request["archive"]["root"])) != request["archive"]:
        raise ValueError("The original causal archive changed")
    for path, pin in zip(request["libraries"].values(), (GEOGRAPHIC_SHA, TRACK_SCORES_SHA, BLOCK_SHA), strict=True):
        checked(Path(path), pin)
    root.mkdir()
    (root / "tmp").mkdir()
    local = root / "detections.json"
    local.write_bytes(data)
    request.update(packet=str(local), cutoff_utc_ns=raw["clock_anchor"]["before"]["realtime_ns"])
    job = root / "binding.json"
    write(job, request)
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    output = root / "publication"
    clock = measure([python, "-IB", __file__, "worker", job, output], env, output)
    write(root / "published-clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])

    result = read(output / "cumulative-grid-worker.json")
    trace = read(output / "direct-residual-audit.json")
    research = read(output / "joint-research-receipt.json")
    receipt = result["receipt"]
    science = pairs.evidence(output, receipt, clock["started_unix_ns"], read_only=True)
    images = artifacts(output, receipt)["images"]
    if (any(science[key] != expected[key] for key in ("arms", "owners", "scientific_digests"))
            or receipt["terminal_sha256"] != expected["terminal_sha256"]
            or research["selected_rows"] != expected["owner_rows"] or len(images) != 8):
        raise ValueError("The paired figure probe changed the sealed science")
    store = FastStandardAnalysisStore(output)
    for name, image in images.items():
        archived = expected["figures"][name]
        if "sha256:" + trace["stock_hashes"][name] != archived["sha256"]:
            raise ValueError("The direct comparison did not draw the archived explicit-layout reference")
        if name in NAMES:
            observed = trace["candidate"][name]["media"]
            if (sha256((root / f"direct-{name}.png").read_bytes()).hexdigest() != image["sha256"].removeprefix("sha256:")
                    or image["rgba_sha256"] != observed["candidate_rgba_sha256"]):
                raise ValueError("Official candidate pixels differ from their checked direct render")
        elif image["sha256"] != archived["sha256"] or image["rgba_sha256"] != archived["rgba_sha256"]:
            raise ValueError("An unrelated official chart changed")
    for name in ("grid", "path"):
        if getattr(store, "position_" + name)(receipt["run_id"])["binding"]["position_png_sha256"] != images["position"]["sha256"]:
            raise ValueError("Position evidence is missing its original figure binding")
    write(root / "result.json", dict(case="DS30-0016", machine=machine, process=clock, worker=result, science=science,
          images=images, render=trace, source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest()
          for name in ("direct-residual-figures-protocol.md", "direct_residual_figures.py", "direct_residual_figures_trial.py")}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("root", type=Path)
        run(parser.parse_args().root)
