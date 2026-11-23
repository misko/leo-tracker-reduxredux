"""Measure one weak orbit pair and, after the gate, a saved full-length transfer."""

import argparse
from contextlib import ExitStack, contextmanager
from functools import partial
import gzip
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import pickle
import subprocess
import sys
from time import process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
RESIDUAL_PIN = "4761ebfc204fbe4fadee953ac7f7976c6a64e1739c4e39645a27581b8fa08b77"
NAMES = tuple(f"ch{prefix}-{view}" for prefix in ("1-4", "5-8") for view in ("all", "unassociated"))


def worker(job, case, mode, output, no_capture=False):
    from aperture_trial import write
    from cumulative_grid_projection import worker as saved
    import unified_short_bootstrap as entry

    original_layout, original = entry.layout_renderer, entry.publish_active
    captured = {}

    @contextmanager
    def observe(scan, enabled, audit, **options):
        with original_layout(scan, enabled, audit, **options):
            render = scan.render

            def record(packet, **options):
                images = render(packet, **options)
                from leo.contracts.fast_standard_analysis import standard_label
                from leo.analysis.research.retained_track_likelihood import PERIOD

                before = process_time_ns()
                model = standard_label(packet["selected_model"])
                frame = packet["position_grid"]
                lat, lon = frame["region_center"]
                title = options["title"] + f" · {frame['box_width_km']:g} km square at ({lat:.5f}°, {lon:.5f}°)"
                subtitle = f"{model} selected result · fitted c · receiver calibration removed; shared phase/orbit corrections included"
                with (output / "orbit-lanes.pickle").open("xb") as stream:
                    pickle.dump((packet["orbit_lanes"], dict(title=title, alias_period_hz=PERIOD, subtitle=subtitle)),
                                stream, protocol=5)
                captured["capture_cpu_ns"] = process_time_ns()-before
                return images

            with patch.object(scan, "render", record):
                yield

    def options(args, *values, **keywords):
        args.direct_residual_figures = case == "weak"
        args.direct_orbit_figures = mode == "native"
        return original(args, *values, **keywords)

    with ExitStack() as stack:
        stack.enter_context(patch.object(entry, "publish_active", options))
        if not no_capture:
            stack.enter_context(patch.object(entry, "layout_renderer", observe))
        saved(job, "installed", output)
    if not no_capture:
        write(output / "orbit-capture.json", captured)


def compare(label, reference, direct):
    import numpy as np
    from matplotlib.colors import to_rgba
    from direct_orbit_figures import GRAY, XLABEL, YLABEL, geometry, lane_ticks

    if (tuple(reference._suptitle.get_text().split("\n")) != direct["headings"]
            or reference.texts[-1].get_text() != direct["footers"][0]
            or tuple(t.get_text() for t in reference.legends[0].get_texts()) != tuple(s for s, _ in direct["legend"])):
        raise ValueError(f"{label} heading, legend or footer changed")
    height, boxes = geometry(direct)
    if tuple(map(int, reference.bbox.size)) != (2400, height):
        raise ValueError("Orbit sheet dimensions differ")

    points = curves = samples = labels = 0
    for index, (axis, row, box) in enumerate(zip(reference.axes, direct["rows"], boxes, strict=True)):
        if (row["titles"][0] != axis.get_title() or direct["xlim"] != axis.get_xlim() or direct["ylim"] != axis.get_ylim()
                or axis.get_ylabel() != YLABEL or axis.get_xlabel() != (XLABEL if index == len(boxes)-1 else "")):
            raise ValueError(f"{label} axis label, count or data limits changed")
        expected = [(GRAY, row["loose"]), *row["associated"]]
        for (color, pairs), art in zip(expected, axis.collections, strict=True):
            if (not np.array_equal(pairs, art.get_offsets()) or not np.array_equal(color, art.get_facecolors()[0, :3])):
                raise ValueError(f"{label} alias-folded peaks, order or colors changed")
            points += len(pairs)
        for (color, pairs), art in zip(row["curves"], axis.lines, strict=True):
            if not (np.array_equal(pairs, art.get_xydata(), equal_nan=True)
                    and np.array_equal(color, to_rgba(art.get_color())[:3])):
                raise ValueError(f"{label} orbit coordinates, phase gaps or colors changed")
            curves += 1
            samples += len(pairs)

        xy = lane_ticks(direct, box)
        old = [(axis.get_yticks(), axis.get_yticklabels(), direct["ylim"], xy[1])]
        if index == len(boxes)-1:
            old.append((axis.get_xticks(), axis.get_xticklabels(), direct["xlim"], xy[0]))
        for original, text, limits, proposed in old:
            selected = [value for value in original if limits[0] <= value <= limits[1]]
            if (len(selected) != len(proposed)
                    or not np.allclose(selected, [x for x, _ in proposed], rtol=0, atol=1e-12)
                    or [item.get_text() for value, item in zip(original, text, strict=True)
                        if limits[0] <= value <= limits[1]] != [name for _, name in proposed]):
                raise ValueError(f"{label} visible tick values or labels changed")
            labels += len(proposed)
    return dict(points=points, curves=curves, samples=samples, tick_labels=labels, lane_axes=len(boxes),
                legend=[name for name, _ in direct["legend"]])


def audit(capture, output):
    import empty_bootstrap as staged
    staged.load_runtime()
    from aperture_trial import write
    from one_pass_web_png import one_pass_layout
    from leo.presentation import orbit_plot
    from tools.pipeline_eval.variants.experimental import raster_layout
    from direct_orbit_figures import scene

    # The worker creates this private file exclusively from its own live packet.
    with capture.open("rb") as stream:
        lanes, options = pickle.load(stream)
    plots = scene(lanes, **options)
    evidence = {}
    with one_pass_layout(enabled=True), patch.object(orbit_plot, "Figure", raster_layout._OrbitFigure):
        for prefix, values in plots.items():
            lo, hi = map(int, prefix.removeprefix("ch").split("-"))
            selected = [lane for lane in lanes if lo <= int(lane.channel[2:]) <= hi]
            chart = orbit_plot.make_orbit_plot(selected, title=f"{options['title']} · CH{lo}–{hi}",
                  alias_period_hz=options["alias_period_hz"], time_limits_s=(0, 300),
                  observation_label="top-one passing GLRT windows", subtitle=options["subtitle"], panel="all")
            evidence[prefix] = compare(prefix, chart, values)
            for lane, row in zip(selected, values["rows"], strict=True):
                loose = sum(peak.satellite_id is None for peak in lane.peaks)
                title = f"{lane.receiver} · {lane.channel} · unassociated only: {loose:,}/{len(lane.peaks):,}"
                if row["titles"][1] != title or len(row["loose"]) != loose:
                    raise ValueError("The native unassociated view changed its original title or counts")
            chart.clear()
    write(output, dict(scientific_axes=evidence, capture_sha256=sha256(capture.read_bytes()).hexdigest()))


def pixels(raw_a, raw_b):
    import numpy as np
    from PIL import Image

    with Image.open(BytesIO(raw_a)) as a, Image.open(BytesIO(raw_b)) as b:
        if (a.size, a.mode, a.info) != (b.size, b.mode, b.info):
            raise ValueError("Native orbit output changed dimensions, mode or metadata")
        delta = np.subtract(np.asarray(a.convert("RGBA")), np.asarray(b.convert("RGBA")), dtype=np.int16)
    return dict(changed_pixel_fraction=float(np.any(delta, axis=2).mean()),
                mean_absolute_rgb_error=float(np.abs(delta[..., :3]).mean()),
                bytes=[len(raw_a), len(raw_b)])


def replay(capture, output):
    """Repaint the immutable live scene without opening the numerical pipeline."""
    import empty_bootstrap as staged
    from aperture_trial import write

    _, spec, _, _, _ = staged.load_runtime()
    from tools.pipeline_eval.variants.experimental import lossless_png, raster_layout
    from direct_orbit_entry import native_orbits
    from direct_orbit_figures import legend_columns, library, surface

    libs = {}
    for key in ("png_filter", "png_deflate"):
        pin = spec[key]
        path = Path(pin["library"])
        staged.checked(path, pin["sha256"])
        libs[key] = path
    encoder = lossless_png.LosslessPng(libs["png_filter"], deflate_library=libs["png_deflate"])
    installed = partial(lossless_png.render_lossless_png, encoder=encoder)
    with capture.open("rb") as stream:
        lanes, options = pickle.load(stream)
    timing = {}
    with native_orbits(installed, timing):
        figures = raster_layout.render_shared(lanes, **options, reuse_pixels=True)
    if timing.get("native_orbit_figures") != 4 or "native_orbit_fallback" in timing:
        raise ValueError("The corrected scene did not retain all four native images")
    from direct_orbit_figures import scene

    gaps = {}
    with surface(library(), 20) as (canvas, _, _):
        for band, plot in scene(lanes, **options).items():
            columns = list(legend_columns(plot["legend"], canvas.text_width))
            separation = [b-a - 46 - max(canvas.text_width(plot["legend"][i][0], 8) for i in group)
                          for (a, group), (b, _) in zip(columns, columns[1:])]
            if not separation or min(separation) < 20:
                raise ValueError("The corrected orbit legend did not reserve label spacing")
            gaps[band] = min(separation)
    output.mkdir()
    for name, data in figures.items():
        (output / f"{name}.png").write_bytes(data)
    write(output / "replay.json", dict(timing=timing, minimum_legend_gap_px=gaps))


def correct(root, weak, dense):
    """One corrected weak native process and a no-solve repaint at both sizes."""
    from aperture_trial import RELEASE, read, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from short_raw_diagnostic import measure, pairs

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh private tmpfs parent")
    weak_data, dense_data = (read(folder / "result.json") for folder in (weak, dense))
    if not weak_data["passed"]:
        raise ValueError("The measured weak trial was ineligible for the correction")
    root.mkdir()
    (root / "tmp").mkdir()
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    output = root / "native"
    clock = measure([python, "-IB", __file__, "worker", weak / "binding.json", "weak", "native", output,
                     "--no-capture"], env, output)
    write(root / "clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])
    executed = read(output / "cumulative-grid-worker.json")
    receipt = executed["receipt"]
    work = executed["layout"]["work"]
    control = weak_data["runs"]["control"]
    science = pairs.evidence(output, receipt, clock["started_unix_ns"], read_only=True)
    research = read(output / "joint-research-receipt.json")
    old = read(weak / "control/joint-research-receipt.json")
    figures = json.loads(json.dumps(artifacts(output, receipt)["images"]))
    store = FastStandardAnalysisStore(output)
    run_id = receipt["run_id"]
    grid = store.position_grid(run_id)
    if (any(science[key] != control["science"][key] for key in ("arms", "owners", "scientific_digests"))
            or receipt["terminal_sha256"] != control["worker"]["receipt"]["terminal_sha256"]
            or research["selected_rows"] != old["selected_rows"]
            or work.get("native_orbit_figures") != 4 or work.get("native_residual_figures") != 2
            or "native_orbit_fallback" in work or not grid["complete"] or grid["evaluated_points"] != 179
            or len(figures) != 8 or (output / "orbit-lanes.pickle").exists()):
        raise ValueError("Corrected weak output changed its signed result or invoked instrumentation")
    if any(v != control["figures"][name] for name, v in figures.items() if name not in NAMES):
        raise ValueError("Correction changed an unrelated official image")
    for name in ("path", "grid"):
        sidecar = getattr(store, "position_" + name)(run_id)
        if sidecar["binding"]["position_png_sha256"] != figures["position"]["sha256"]:
            raise ValueError("The official position image lost its numerical sidecar")

    corrected = {}
    for name, prior, folder, original_root in (
        ("weak", weak_data, weak, weak / "control"),
        ("dense", dense_data, dense, Path("/dev/shm/leo-cumulative-grid-projection-01/dense-pair/installed")),
    ):
        stage = root / f"corrected-{name}"
        capture = folder / "native/orbit-lanes.pickle"
        if sha256(capture.read_bytes()).hexdigest() != prior["scene"]["capture_sha256"]:
            raise ValueError("The sealed live plot scene changed")
        subprocess.run([python, "-IB", __file__, "replay", capture, stage], check=True, env=env, timeout=30)
        native = prior["runs"]["native"]["worker"]["receipt"]["run_id"]
        original = FastStandardAnalysisStore(original_root)
        before = prior["runs"].get("control", prior["runs"]["native"])["figures"]
        visual, digests = {}, {}
        for key in NAMES:
            raw = (stage / f"{key}.png").read_bytes()
            if name == "weak" and store.artifact(run_id, key, figures[key]["sha256"]) != raw:
                raise ValueError("Production-shaped weak rendering used a different corrected live scene")
            original_raw = original.artifact(native, key, before[key]["sha256"]) if name == "weak" else original.artifact(native, key)
            visual[key] = pixels(original_raw, raw)
            digests[key] = sha256(raw).hexdigest()
        corrected[name] = dict(**read(stage / "replay.json"), visual=visual, sha256=digests)
    write(root / "result.json", dict(machine=machine, control_process=control["process"], native_process=clock,
          earlier_control_capture_cpu_ns=control["capture"]["capture_cpu_ns"],
          outcome=executed, science=science, figures=figures, corrected=corrected,
          prior_result_sha256={name: sha256((folder / "result.json").read_bytes()).hexdigest()
                              for name, folder in (("weak", weak), ("dense", dense))},
          source_sha256={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
              "direct_orbit_figures.py", "direct_orbit_entry.py", "direct_orbit_figures_trial.py",
              "unified_short_bootstrap.py", "direct-orbit-figures-protocol.md",
          )}))


def run(case, root, weak):
    from aperture_trial import RELEASE, archive_identity, read, write
    from combined_frontier_run import BLOCK_SHA
    from cumulative_grid_projection import enrolled, proof_fields
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from short_raw_diagnostic import measure, pairs
    from unified_short_bootstrap import LAYOUT_SHA256

    machine = host()
    if (case == "dense" and (weak is None or not read(weak)["passed"])):
        raise ValueError("The weak elapsed and equivalence gate must pass before full-length transfer")
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", root.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use a fresh private tmpfs parent")
    request, packet, expected = enrolled(case)
    data = checked(packet, request["native"].removeprefix("sha256:"))
    source = json.loads(data)
    if archive_identity(Path(request["archive"]["root"])) != request["archive"]:
        raise ValueError("The original causal archive changed")
    for path, pin in zip(request["libraries"].values(), (GEOGRAPHIC_SHA, TRACK_SCORES_SHA, BLOCK_SHA), strict=True):
        checked(Path(path), pin)
    checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    expected_media = expected["figures"]
    archived_root = None
    if case == "weak":
        prior = checked(HERE / "measurements/direct-residual-entry-DS30-0016.json.gz", RESIDUAL_PIN)
        expected_media = json.loads(gzip.decompress(prior))["runs"]["native"]["figures"]
    else:
        archived_root = Path("/dev/shm/leo-cumulative-grid-projection-01/dense-pair/installed")
        if not archived_root.is_dir():
            raise ValueError("The exact same-packet dense rendered control is unavailable")

    root.mkdir()
    (root / "tmp").mkdir()
    local = root / "detections.json"
    local.write_bytes(data)
    request.update(packet=str(local), cutoff_utc_ns=source["clock_anchor"]["before"]["realtime_ns"])
    job = root / "binding.json"
    write(job, request)
    env, python = environment(root), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(root / "tmp")
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   check=True, env=env, timeout=30)
    order = ("control", "native") if case == "weak" else ("native",)
    clocks = {}
    for mode in order:
        dest = root / mode
        clocks[mode] = measure([python, "-IB", __file__, "worker", job, case, mode, dest], env, dest)
        write(root / f"{mode}-clock.json", clocks[mode])
        if clocks[mode]["exit_code"]:
            raise RuntimeError(clocks[mode]["stderr_tail"])

    runs = {}
    for mode in order:
        dest = root / mode
        executed = read(dest / "cumulative-grid-worker.json")
        receipt = executed["receipt"]
        science = pairs.evidence(dest, receipt, clocks[mode]["started_unix_ns"], read_only=True)
        figures = json.loads(json.dumps(artifacts(dest, receipt)["images"]))
        research = read(dest / "joint-research-receipt.json")
        regional, = research["early_regional"]
        store = FastStandardAnalysisStore(dest)
        grid = store.position_grid(receipt["run_id"])
        native = mode == "native"
        work = executed["layout"]["work"]
        if (receipt["terminal_sha256"] != expected["terminal_sha256"] or research["selected_rows"] != expected["owner_rows"]
                or any(science[key] != expected[key] for key in ("arms", "owners", "scientific_digests"))
                or proof_fields(regional) != expected["proof"] or not grid["complete"] or grid["evaluated_points"] != 179
                or len(figures) != 8 or executed["handoffs"] != 1 or executed["waveform_calls"]
                or work.get("native_orbit_figures", 0) != (4 if native else 0) or "native_orbit_fallback" in work
                or work.get("orbit_figures", 0) != (0 if native else 2)):
            raise ValueError(f"{mode} changed the archived scientific or configured renderer route: {work!r}")
        if any(figure != expected_media[name] for name, figure in figures.items() if not native or name not in NAMES):
            raise ValueError("An unrelated official image changed")
        for name in ("path", "grid"):
            sidecar = getattr(store, "position_" + name)(receipt["run_id"])
            if sidecar["binding"]["position_png_sha256"] != figures["position"]["sha256"]:
                raise ValueError("Position evidence changed its original official image binding")
        runs[mode] = dict(worker=executed, science=science, figures=figures, process=clocks[mode],
                         capture=read(dest / "orbit-capture.json"))

    original_root = root / "control" if case == "weak" else archived_root
    if case == "weak" and (original_root / "orbit-lanes.pickle").read_bytes() != (root / "native/orbit-lanes.pickle").read_bytes():
        raise ValueError("The paired draw modes received different live observations, predicted curves or title")
    original, native = (FastStandardAnalysisStore(folder) for folder in (original_root, root / "native"))
    run_id = runs["native"]["worker"]["receipt"]["run_id"]
    visual = {name: pixels(original.artifact(run_id, name, expected_media[name]["sha256"]),
                          native.artifact(run_id, name, runs["native"]["figures"][name]["sha256"])) for name in NAMES}
    observed = root / "orbit-scene-audit.json"
    subprocess.run([python, "-IB", __file__, "audit", root / "native/orbit-lanes.pickle", observed],
                   check=True, env=env, timeout=30)
    passed = case == "weak" and clocks["control"]["elapsed_s"] - clocks["native"]["elapsed_s"] >= .150
    write(root / "result.json", dict(case=case, passed=passed, runs=runs, visual=visual, scene=read(observed),
          machine=machine, inputs=request, archived_control=None if case == "weak" else
          read(archived_root.with_name("result.json"))["runs"]["installed"]["clock"],
          source_sha256={name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
              "direct_orbit_figures.py", "direct_orbit_entry.py", "direct_orbit_figures_trial.py",
              "unified_short_bootstrap.py", "direct-orbit-figures-protocol.md",
          )}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_subparsers(dest="action", required=True)
    member = modes.add_parser("worker")
    member.add_argument("job", type=Path)
    member.add_argument("case", choices=("weak", "dense"))
    member.add_argument("mode", choices=("control", "native"))
    member.add_argument("output", type=Path)
    member.add_argument("--no-capture", action="store_true")
    exact = modes.add_parser("audit")
    exact.add_argument("capture", type=Path)
    exact.add_argument("output", type=Path)
    render = modes.add_parser("replay")
    render.add_argument("capture", type=Path)
    render.add_argument("output", type=Path)
    correction = modes.add_parser("correct")
    for name in ("root", "weak", "dense"):
        correction.add_argument(name, type=Path)
    pair = modes.add_parser("run")
    pair.add_argument("case", choices=("weak", "dense"))
    pair.add_argument("root", type=Path)
    pair.add_argument("--weak", type=Path)
    args = vars(parser.parse_args())
    {"worker": worker, "audit": audit, "replay": replay, "run": run, "correct": correct}[args.pop("action")](**args)
