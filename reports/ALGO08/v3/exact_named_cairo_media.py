"""Check the official scientific and media outputs of the named Cairo pilot."""

from contextlib import contextmanager
from functools import partial
from hashlib import sha256
import pickle
from pathlib import Path
from unittest.mock import patch


def image_hashes(images):
    return {name: "sha256:" + sha256(image).hexdigest() for name, image in images.items()}


def act(work):
    if (work.get("native_orbit_figures") != 4 or work.get("native_residual_figures") != 2
            or any("fallback" in key for key in work)):
        raise ValueError(f"Expected all six native sheets with no fallback: {work}")


def orbit_evidence(lanes, options, scenes):
    import direct_orbit_figures as orbit
    from direct_orbit_figures_trial import compare
    from leo.presentation import orbit_plot
    from one_pass_web_png import one_pass_layout
    from tools.pipeline_eval.variants.experimental import raster_layout

    evidence = {}
    with orbit.surface(orbit.library(), 20) as (canvas, _, _), one_pass_layout(enabled=True):
        with patch.object(orbit_plot, "Figure", raster_layout._OrbitFigure):
            for band, scene in scenes.items():
                low, high = map(int, band.removeprefix("ch").split("-"))
                selected = [lane for lane in lanes if low <= int(lane.channel[2:]) <= high]
                with clear_fig(orbit_plot.make_orbit_plot(selected, title=f"{options['title']} · CH{low}–{high}",
                        alias_period_hz=options["alias_period_hz"], time_limits_s=(0, 300),
                        observation_label="top-one passing GLRT windows", subtitle=options["subtitle"],
                        panel="all")) as figure:
                    summary = compare(band, figure, scene)
                    for lane, row in zip(selected, scene["rows"], strict=True):
                        loose = sum(item.satellite_id is None for item in lane.peaks)
                        if (len(row["loose"]) != loose or row["titles"][1] !=
                                f"{lane.receiver} · {lane.channel} · unassociated only: {loose:,}/{len(lane.peaks):,}"):
                            raise ValueError("Unassociated figure changed its chart scope")
                columns = list(orbit.legend_columns(scene["legend"], canvas.text_width))
                gaps = [b-a-46-max(canvas.text_width(scene["legend"][i][0], 8) for i in group)
                        for (a, group), (b, _) in zip(columns, columns[1:])]
                if gaps and min(gaps) < 20:
                    raise ValueError("Orbit legend labels overlap")
                evidence[band] = summary | {"minimum_legend_gap_px": min(gaps) if gaps else None}
    return evidence


@contextmanager
def clear_fig(figure):
    try:
        yield figure
    finally:
        figure.clear()


def replay(case, output):
    from empty_bootstrap import checked, clock, load_runtime, now

    _, spec, _, _, _ = load_runtime()
    from aperture_trial import read, write
    import direct_orbit_figures as orbit
    from direct_residual_figures import cairo_library, raster, scene
    from direct_residual_figures_trial import NAMES, compare_scene, pixels, stock_scene
    from exact_named_cairo import SCENE, control, draw_cairo, pins
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng, render_lossless_png

    if read(output / "binding.json")["renderer_sources"] != pins():
        raise ValueError("The paid renderer source changed")
    worker = read(output / "render.json")
    # This is the one private scene written by this successful timed worker.
    data = checked(output / SCENE, worker["live_scene_sha256"])
    packet, options = pickle.loads(data)
    native_inputs = {}
    for name in ("png_filter", "png_deflate"):
        pin = spec[name]
        native_inputs[name] = Path(pin["library"])
        checked(native_inputs[name], pin["sha256"])
    installed = partial(render_lossless_png, encoder=LosslessPng(native_inputs["png_filter"],
                                                                  deflate_library=native_inputs["png_deflate"]))
    _, former = control(case)
    expected = former["artifacts"]["candidate"]["products"]["images"]
    sequence = now()
    start = now()
    original = installed(packet, **options)
    stock_clock = clock(start)
    if image_hashes(original) != {name: item["sha256"] for name, item in expected.items()}:
        raise ValueError("The exact live packet did not reproduce all eight original stock files")

    original_draw, original_scene = FigureCanvasAgg.draw, orbit.scene
    stock_axes, captures, direct_audit = [], [], {}

    def stock_observer(canvas, *args, **kwargs):
        result = original_draw(canvas, *args, **kwargs)
        if tuple(canvas.figure.get_size_inches()) == (15, 11):
            stock_axes.append(stock_scene(canvas.figure))
        return result

    def orbit_observer(lanes, **values):
        chart = original_scene(lanes, **values)
        captures.append((lanes, values, chart))
        return chart

    with patch.object(orbit, "scene", orbit_observer):
        candidate = draw_cairo(installed, packet, direct_audit, **options)
    act(direct_audit["work"])
    with patch.object(FigureCanvasAgg, "draw", stock_observer):
        if installed(packet, **options) != original:
            raise ValueError("Stock artist audit changed the reference media")
    (lanes, orbit_options, direct_orbits), = captures
    orbital = orbit_evidence(lanes, orbit_options, direct_orbits)
    cairo = cairo_library()
    residuals = {}
    chapters = scene(packet, options["title"])
    for name, axes in zip(NAMES, stock_axes, strict=True):
        _, ticks = raster(chapters[name], cairo)
        comparison = compare_scene(axes, chapters[name], ticks)
        residuals[name] = comparison | {"axes_limits": [list(a["ylim"]) for a in axes["axes"]]}

    write(output / "replay.json", dict(stock_images=image_hashes(original), candidate_images=image_hashes(candidate),
           render_stock=stock_clock, render_cairo=direct_audit, offline_total=clock(sequence),
           orbits=orbital, residuals=residuals, media={name: pixels(original[name], candidate[name]) for name in original},
           live_scene_sha256=worker["live_scene_sha256"]))


def verify(case, output):
    import sys
    from aperture_trial import read, write
    from exact_named_cairo import CHANGED, ROOT, control, pins

    # Use the current read-only storage verifier after the installed process exits.
    sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified
    from leo.contracts.fast_standard_analysis import PLOTS
    from publication_media_checks import verify_position_sidecars

    baseline, original = control(case)
    binding = read(output / "binding.json")
    if binding["renderer_sources"] != pins() or binding["exact_control"] != str(baseline):
        raise ValueError("The published scene must bind the frozen case and renderer")
    req = read(Path(binding["input"]["request"]))
    clock = read(output / "clock.json")
    draw, replayed = (read(output / name) for name in ("render.json", "replay.json"))
    act(draw["work"])
    before = verified(baseline / "candidate", original["clocks"]["candidate"], "worker.json", req)
    current = verified(output / "candidate", clock, "worker.json", req)
    checks = parity(before, current)
    checks.pop("eight_pngs")
    current_ports, baseline_ports = current["trace"], before["trace"]
    if (not all(checks.values()) or not all(run["sample"]["complete"] and run["sample"]["evaluated_points"] == 179
                                           for run in (before, current))
            or not current_ports["stock_control"] or current_ports["early_regional"] != baseline_ports["early_regional"]):
        raise ValueError(f"The named publication changed a scientific field: {checks}")
    old, new = (report["products"]["images"] for report in (before, current))
    unchanged = {name for name in old if old[name] == new[name]}
    if (set(old) != set(new) or set(new) != set(PLOTS) or set(new)-unchanged != CHANGED
            or any(replayed["candidate_images"][name] != item["sha256"] for name, item in new.items())
            or replayed["live_scene_sha256"] != draw["live_scene_sha256"]):
        raise ValueError("The original eight media bindings and scoped Cairo substitutions differ")
    run_id = current["worker"]["receipt"]["run_id"]
    sidecars = verify_position_sidecars(baseline/"candidate", output/"candidate", run_id, old, new)
    elapsed_saving = original["clocks"]["candidate"]["elapsed_s"]-clock["elapsed_s"]
    render_saving = replayed["render_stock"]["cpu_s"]-draw["render"]["cpu_s"]
    speed = {metric: original["clocks"]["named"][metric]/clock[metric] for metric in ("cpu_s", "elapsed_s")}
    write(output / "result.json", dict(case="DS30-" + case, sources=pins(), exact_checks=checks, sidecars=sidecars,
           clocks=original["clocks"] | {"cairo": clock}, elapsed_saving_s=elapsed_saving, render_saving_cpu_s=render_saving,
           speedup_vs_named=speed, transfer_ready=(elapsed_saving > 0 and render_saving > 0), render=draw, replay=replayed,
           science=current["science"], geography=original["geography"], outputs=new, stock_outputs=old,
           unchanged_figures=sorted(unchanged), grid_points=179, backing_reads=0, waveform_reads=0))
