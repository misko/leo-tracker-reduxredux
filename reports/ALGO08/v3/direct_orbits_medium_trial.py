"""Time the corrected orbit opt-in on the sealed DS30-0057 publication."""

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
PRIOR = Path("/dev/shm/leo-cumulative-medium.OBSGQ15J/pair")
PINS = {
    "binding.json": "2690934ebd8df12b3a9eab50cad06b091984780ab24bfeff316536d0271afb44",
    "result.json": "8b716e18d0275e259d2541587662980515d0781a328a923c0982b16995bf534b",
    "candidate/joint-research-receipt.json": "f9ff8b1566e88746c50016158abbacfe506b717f0603f897d6708b135db95f7c",
}
MODES = ("control", "native")


def worker(job, mode, output):
    from cumulative_grid_projection import worker as saved_publication
    import unified_short_bootstrap as entry

    installed = entry.publish_active

    def configured(args, *values, **options):
        args.direct_residual_figures = True
        args.direct_orbit_figures = mode == "native"
        return installed(args, *values, **options)

    with patch.object(entry, "publish_active", configured):
        saved_publication(job, "installed", output)


def neighborhood_match(left, right):
    """Compare colored curve footprints in displayed space, with 2 px tolerance."""
    import numpy as np
    from scipy.ndimage import maximum_filter

    a, b = (np.ptp(pixels, axis=2) >= 32 for pixels in (left, right))
    if not a.any() or not b.any():
        raise ValueError("Expected colored orbit markings in both renderers")
    return [float(np.count_nonzero(p & maximum_filter(q, size=5, mode="constant")) / np.count_nonzero(p))
            for p, q in ((a, b), (b, a))]


def inspect_orbits(store_a, store_b, run_id, pictures, owners):
    import numpy as np
    from matplotlib import colormaps
    from PIL import Image
    from direct_orbit_figures import DPI, GRAY, WIDTH, legend, legend_columns, library, surface
    from direct_orbit_figures_trial import NAMES, pixels

    satellite_ids = sorted({str(row[1]) for row in owners})
    palette = colormaps["turbo"]
    entries = [("Unassociated", GRAY), *((sat, palette((i+.5)/len(satellite_ids))[:3])
               for i, sat in enumerate(satellite_ids))]
    rows = math.ceil(len(entries)/6)
    results = {}
    c = library()
    for name in NAMES:
        raw_a = store_a.artifact(run_id, name, pictures["control"][name]["sha256"])
        raw_b = store_b.artifact(run_id, name, pictures["native"][name]["sha256"])
        result = pixels(raw_a, raw_b)
        with Image.open(BytesIO(raw_a)) as a, Image.open(BytesIO(raw_b)) as b:
            first, second = (np.array(img.convert("RGB")) for img in (a, b))
        height = first.shape[0]
        footer = (.5 + .25*rows + .62)*DPI + max(0., .025*height-.50*DPI)
        lane = np.s_[int(1.37*DPI)+2:int(height-footer)-2, int(WIDTH*.07)+2:int(WIDTH*.97)-2]
        support = neighborhood_match(first[lane], second[lane])
        if min(support) < .98:
            raise ValueError(f"Visible colored orbit footprints disagree for {name}: {support!r}")

        last = height*.975 - 24
        banner = slice(int(last - (rows-1)*22 - 26), int(last + 12))
        with surface(c, height) as (canvas, surface_id, output):
            canvas.ink(1., 1., 1.)
            c.cairo_paint(canvas.ctx)
            legend(canvas, entries, height)
            c.cairo_surface_flush(surface_id)
            columns = list(legend_columns(entries, canvas.text_width))
            separation = [x1-x0 - 46 - max(canvas.text_width(entries[i][0], 8) for i in group)
                          for (x0, group), (x1, _) in zip(columns, columns[1:])]
            if (min(separation) < 20 or not np.array_equal(output[banner, :, 2::-1], second[banner])):
                raise ValueError(f"Native legend for {name} does not reproduce its sealed owner labels")
        results[name] = dict(**result, neighborhood_fraction=support, minimum_legend_gap_px=min(separation))
    return dict(figures=results, legend_satellites=satellite_ids)


def run(output):
    from aperture_trial import RELEASE, archive_identity, read, write
    from combined_frontier_run import BLOCK_SHA
    from cumulative_grid_projection import proof_fields
    from dense_geographic_trial import host
    from direct_orbit_figures_trial import NAMES
    from empty_bootstrap import checked
    from full_short_physical import environment
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from joint_publication import artifacts
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from local_future_cli_trial import native_packet
    from short_raw_diagnostic import measure, pairs
    from unified_short_bootstrap import LAYOUT_SHA256

    machine = host()
    if subprocess.check_output(["findmnt", "-no", "FSTYPE", "-T", output.parent], text=True).strip() != "tmpfs":
        raise ValueError("Use new private tmpfs outputs for both medium launches")
    job, witness, original = (json.loads(checked(PRIOR / name, pin)) for name, pin in PINS.items())
    original_arm = witness["runs"]["candidate"]
    admission = witness["admission"]
    expected = original_arm["evidence"]
    packet = native_packet(PRIOR / "candidate")
    native_sha = job["native"]["candidate"]
    data = json.loads(checked(packet, native_sha.removeprefix("sha256:")))
    if (witness["case"] != "DS30-0057" or not original_arm["audit"]["checks"]["artists_and_overlap"]
            or admission["admission"] != "saved" or archive_identity(Path(job["archive"]["root"])) != job["archive"]
            or original["receipt"]["terminal_sha256"] != expected["receipt"]["terminal_sha256"]):
        raise ValueError("The enrolled sealed medium fix changed")
    pins = dict(geographic_library=GEOGRAPHIC_SHA, regional_track_library=TRACK_SCORES_SHA,
                frontier_block_library=BLOCK_SHA)
    libraries = {name: Path(job[name]) for name in pins}
    for name, path in libraries.items():
        checked(path, pins[name])
    checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    output.mkdir()
    temporary = output / "tmp"
    temporary.mkdir()
    request = output / "binding.json"
    write(request, dict(recording=job["recording"], archive=job["archive"], region=job["region"],
          libraries={name: str(path) for name, path in libraries.items()},
          packet=str(packet), native=native_sha, cutoff_utc_ns=data["clock_anchor"]["before"]["realtime_ns"],
          authority=job["raw_authority"], session=admission["session"], inventory=job["input_manifest"],
          issued=admission["issue"], offer_sha256=job["region_sha256"]))
    env, python = environment(output), RELEASE / "venv/bin/python"
    env["TMPDIR"] = str(temporary)
    subprocess.run([python, "-Bc", "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    timings = {}
    for mode in MODES:
        target = output / mode
        command = [python, "-IB", __file__, "worker", request, mode, target]
        timings[mode] = measure(command, env, target)
        write(output / f"{mode}-clock.json", dict(clock=timings[mode], command=list(map(str, command))))
        if timings[mode]["exit_code"]:
            raise RuntimeError(timings[mode]["stderr_tail"])

    results = {}
    stores = {mode: FastStandardAnalysisStore(output / mode) for mode in MODES}
    for mode, store in stores.items():
        target = output / mode
        run = read(target / "cumulative-grid-worker.json")
        research = read(target / "joint-research-receipt.json")
        receipt = run["receipt"]
        run_id = receipt["run_id"]
        science = pairs.evidence(target, receipt, timings[mode]["started_unix_ns"], read_only=True)
        figures = json.loads(json.dumps(artifacts(target, receipt)["images"]))
        grid = store.position_grid(run_id)
        work = run["layout"]["work"]
        if (receipt["terminal_sha256"] != expected["receipt"]["terminal_sha256"]
                or any(science[key] != expected[key] for key in ("arms", "owners", "scientific_digests", "raw_authority"))
                or research["selected_rows"] != original["selected_rows"]
                or proof_fields(research["early_regional"][0]) != proof_fields(original["early_regional"][0])
                or sha256(native_packet(target).read_bytes()).hexdigest() != native_sha.removeprefix("sha256:")
                or not grid["complete"] or grid["evaluated_points"] != 179 or len(figures) != 8
                or run["handoffs"] != 1 or run["waveform_calls"] or run["graph"]["enabled"] or run["projection"] is not None
                or work.get("native_orbit_figures", 0) != (4 if mode == "native" else 0)
                or work.get("orbit_figures", 0) != (0 if mode == "native" else 2)
                or work.get("native_residual_figures") != 2
                or any("fallback" in key for key in work) or (target / "orbit-lanes.pickle").exists()):
            raise ValueError(f"{mode} did not use the intended clean route and archived science: {work!r}")
        for name in ("grid", "path"):
            if getattr(store, "position_" + name)(run_id)["binding"]["position_png_sha256"] != figures["position"]["sha256"]:
                raise ValueError("The numerical evidence lost its actual position PNG binding")
        results[mode] = dict(worker=run, process=timings[mode], science=science, figures=figures)

    baseline, candidate = (results[mode]["figures"] for mode in MODES)
    if (any(baseline[name] != original_arm["figures"][name] for name in (*NAMES, "track-rms", "position"))
            or {name for name in baseline if baseline[name] != candidate[name]} != set(NAMES)):
        raise ValueError("The four unchanged and four native official figures differed from their intended routes")
    visual = inspect_orbits(*(stores[mode] for mode in MODES), run_id, {mode: results[mode]["figures"] for mode in MODES},
                            original["selected_rows"]["fitted_c"])
    write(output / "result.json", dict(case="DS30-0057", machine=machine, order=MODES, prior_sources=PINS,
          runs=results, visual=visual, input=read(request), source_sha256={name: sha256((HERE/name).read_bytes()).hexdigest()
          for name in ("direct_orbits_medium_trial.py", "direct-orbits-medium-protocol.md", "direct_orbit_entry.py",
                       "direct_orbit_figures.py", "direct_residual_entry.py", "unified_short_bootstrap.py")}))


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    if sys.argv[1:2] == ["worker"]:
        parser.add_argument("job", type=Path)
        parser.add_argument("mode", choices=MODES)
        parser.add_argument("output", type=Path)
        worker(**vars(parser.parse_args(sys.argv[2:])))
    else:
        parser.add_argument("output", type=Path)
        run(parser.parse_args().output)
