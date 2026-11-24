"""Use six qualified Cairo sheets on the unmodified exact named numerical entry."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
import pickle
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
CONTROLS = {
    "0160": ("/dev/shm/leo-v3-exact-named-0160-result01", "dd1f4a2f3891bba9a5ae9985f87273117223b137e398f39334e5b6edb3e1016b"),
    "0316": ("/dev/shm/leo-v3-exact-named-0316-result02", "f53bfaad5a6b849398dce78bd7669c6d845f6bd886474a96ce71981c49464bc8"),
}
CHANGED = frozenset(f"{band}-{role}" for band in ("ch1-4", "ch5-8") for role in ("all", "unassociated", "residuals"))
SCENE = "live-render.pickle"
CONTROLLED_SOURCES = tuple(HERE / name for name in (
    "exact-named-cairo-protocol.md", "exact_named_cairo.py", "exact_named_cairo_media.py", "exact_named_route.py",
    "direct_orbit_figures.py", "direct_orbit_entry.py", "direct_residual_figures.py", "direct_residual_entry.py",
    "direct_orbit_figures_trial.py", "direct_residual_figures_trial.py", "one_pass_web_png.py",
))


def pins():
    return {path.name: sha256(path.read_bytes()).hexdigest() for path in CONTROLLED_SOURCES}


def control(case):
    from empty_bootstrap import checked
    from held_adaptive_0160 import resident_path

    root, pin = CONTROLS[case]
    root = resident_path(Path(root))
    receipt = json.loads(checked(root / "result.json", pin))
    if receipt["case"] != "DS30-" + case or not receipt["exact"]:
        raise ValueError("Require the same complete exact named saved control")
    return root, receipt


def draw_cairo(installed, packet, audit, **options):
    from direct_orbit_entry import native_orbits
    from direct_residual_entry import render
    from empty_bootstrap import clock, now

    start = now()
    orbit = {}
    with native_orbits(installed, orbit):
        images, residual = render(installed, packet, explicit_layout=False, **options)
    audit.update(work=orbit | residual, render=clock(start))
    return images


def worker(case, output):
    import exact_named_route as exact
    from empty_bootstrap import clock, now

    request = exact.read(output / "binding.json")
    if request["renderer_sources"] != pins():
        raise ValueError("The renderer trial differs from its frozen sources")
    renderer = request.get("renderer", "cairo")
    capture = request.get("scene_capture", True)
    exact_ports, timing, scenes = exact.exact_ports, {}, []

    @contextmanager
    def guarded(*args, **kwargs):
        from tools import algo08_scan

        original = algo08_scan.render

        def generate(packet, **options):
            if timing:
                raise ValueError("Expected a single actual named render request")
            if capture:
                scenes.append((packet, options))
            if renderer == "cairo":
                return draw_cairo(original, packet, timing, **options)
            start = now()
            rendered = original(packet, **options)
            timing.update(work={}, render=clock(start))
            return rendered

        with exact_ports(*args, **kwargs), patch.object(algo08_scan, "render", generate):
            yield

    with patch.object(exact, "exact_ports", guarded):
        exact.worker(case, output)
    from aperture_trial import write

    if capture:
        (scene,) = scenes
        start = now()
        payload = pickle.dumps(scene, protocol=pickle.HIGHEST_PROTOCOL)
        with (output / SCENE).open("xb") as stream:
            stream.write(payload)
        timing.update(live_scene_sha256=sha256(payload).hexdigest(), live_scene_bytes=len(payload), capture=clock(start))
    write(output / "render.json", timing | dict(renderer=renderer, scene_capture=capture))


def launch(case, output, first, *, renderer="cairo", scene_capture=True):
    import exact_named_route as exact
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from held_adaptive_0160 import resident_path
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    machine = host()
    if case == "0316":
        if first is None:
            raise ValueError("Seal the DS30-0160 candidate before transfer")
        result = exact.read(resident_path(first / "result.json"))
        if result["case"] != "DS30-0160" or result["sources"] != pins() or not result["transfer_ready"]:
            raise ValueError("The first positive publication did not pass the transfer gate")
    baseline, prior = control(case)
    enrollment = exact.bind(case)
    expected_sources = enrollment["sources"]
    if case == "0160":
        # Its original worker predates the audited legacy manifest normalization.
        expected_sources = expected_sources | {"exact_named_route.py": exact.FIRST_DRIVER_SHA256}
    if (enrollment["packets"] != prior["enrollment"]["input"]["packets"]
            or expected_sources != prior["source_bindings"]
            or not resident_path(output.parent).is_relative_to("/dev/shm") or output.exists()):
        raise ValueError("Expected the exact same signed request in a fresh tmpfs output")
    _, refs = exact.checked_catalogue(enrollment, exact.read(Path(enrollment["request"])), TleArchiveReader, canonical_digest)
    resident = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(ref.path for ref in refs)], text=True))["fincore"]
    if len(resident) != len(refs) or any(row["res"] < row["size"] for row in resident):
        raise ValueError("The exact authentication view must already be resident")
    output.mkdir(mode=0o700)
    (output / "fonts").mkdir()
    (output / "tmp").mkdir()
    for path in (Path(enrollment["stage"]) / "fonts").glob("fontlist-*.json"):
        (output / "fonts" / path.name).hardlink_to(resident_path(path))
    command = ["/usr/bin/timeout", "--kill-after=2s", "55s", RELEASE / "venv/bin/python", "-IB",
               Path(__file__), "worker", case, output]
    env = environment(output) | {"TMPDIR": str(output / "tmp"), "XDG_CACHE_HOME": str(output / "tmp")}
    write(output / "binding.json", dict(input=enrollment, machine=machine, command=list(map(str, command)),
        exact_control=str(baseline), exact_control_sha256=CONTROLS[case][1], renderer_sources=pins(),
        resident_bodies=len(refs), resident_bytes=sum(row["size"] for row in resident),
        renderer=renderer, scene_capture=scene_capture))
    clock = measure(command, env, output / "candidate")
    write(output / "clock.json", clock)
    if clock["exit_code"]:
        raise RuntimeError(clock["stderr_tail"])


def paired(case, output, first):
    from aperture_trial import read, write
    from exact_named_cairo_media import capture_sources
    from held_adaptive_0160 import resident_path

    if first is None or case != "0160" or resident_path(output.parent) != Path("/dev/shm"):
        raise ValueError("The single authorized saved pair needs the first verified 0160 audit")
    first = resident_path(first)
    prior = read(first / "result.json")
    if (prior["sources"] != capture_sources() or prior["case"] != "DS30-0160"
            or not all(prior["exact_checks"].values()) or prior["render_saving_cpu_s"] < .15
            or prior["transfer_ready"]):
        raise ValueError("The initial sealed scientific and rendering gate is required")
    output.mkdir(mode=0o700)
    followup = HERE / "exact-named-cairo-followup.md"
    write(output / "pair-binding.json", dict(first=str(first), first_result_sha256=sha256((first/"result.json").read_bytes()).hexdigest(),
          order=("stock", "cairo"), source_pins=pins(), followup_sha256=sha256(followup.read_bytes()).hexdigest()))
    for mode in ("stock", "cairo"):
        launch(case, output / mode, None, renderer=mode, scene_capture=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "replay", "verify", "pair", "verify-pair"))
    parser.add_argument("case", choices=CONTROLS)
    parser.add_argument("output", type=Path)
    parser.add_argument("--first", type=Path)
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.case, args.output, args.first)
    elif args.action == "worker":
        worker(args.case, args.output)
    elif args.action == "pair":
        paired(args.case, args.output, args.first)
    else:
        from exact_named_cairo_media import replay, verify, verify_pair

        {"replay": replay, "verify": verify, "verify-pair": verify_pair}[args.action](args.case, args.output)
