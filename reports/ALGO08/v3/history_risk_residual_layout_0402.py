"""Exercise the ordinary-orbit Cairo layout on archived and live saved plotting packets."""

import argparse
from contextlib import contextmanager
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import pickle
import sys
from types import SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))

from exact_named_cairo import SCENE
from history_risk_cairo_0402 import CONTROL, ORBIT_SHEETS, PRIOR, controls, read, source_digest


ARCHIVED_SCENE = Path("/dev/shm/leo-v3-exact-named-cairo-0316-result01/live-render.pickle")
ARCHIVED_SHA = "4559edff28db01b962e3187572d4cb11bc2a4bbf9d7d9aff9cb0a305a2c33330"
ALL_CAIRO = Path("/dev/shm/leo-v3-history-risk-cairo-0402-result01/verified-result.json")
ALL_CAIRO_SHA = "82a177ef8ea46681c9021ab830cdaa7f737f1ad633f644890a06ce742aac239f"
PROTOCOL = "history-risk-residual-layout-0402-protocol.md"
TIMED_DRIVER = "228c630d85af623075c000b83d9ef045255d0cbae1ea963e76183e205ab5efea"
PREVIOUS_DRIVER = "242c64ac306d0f8ffbbadfa999677ec83583bb19f2beda46053f8c671971ebbd"


def source_pins():
    from history_cairo_render import RESIDUAL_SOURCES

    names = (*RESIDUAL_SOURCES, Path(__file__).name, PROTOCOL, "exact_named_raw.py", "history_risk_cairo_0402.py")
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in names}


def require_active(audit):
    if (tuple(audit.get(key) for key in ("native_residual_figures", "position_figures", "track_figures")) != (2, 1, 1)
            or [draw["figures"] for draw in audit.get("ordinary_orbit_draws", [])] != [4]
            or any("fallback" in key or key in ("native_orbit_figures", "orbit_figures") for key in audit)):
        raise ValueError(f"The ordinary orbit and four optimized figures must all execute once: {audit}")


def media_identity(images):
    return {name: (item["sha256"], item["rgba_sha256"], tuple(item["size"])) for name, item in images.items()}


def render_pair(path, digest):
    from empty_bootstrap import checked, clock, load_runtime, now

    _, spec, _, _, _ = load_runtime()
    from exact_named_cairo_media import image_hashes
    from history_cairo_render import binding
    from tools.pipeline_eval.variants.experimental.lossless_png import LosslessPng, render_lossless_png

    packet, options = pickle.loads(checked(path, digest))
    libraries = {}
    for name in ("png_filter", "png_deflate"):
        pin = spec[name]
        libraries[name] = Path(pin["library"])
        checked(libraries[name], pin["sha256"])
    installed = partial(render_lossless_png, encoder=LosslessPng(libraries["png_filter"],
                                                                 deflate_library=libraries["png_deflate"]))
    audit = {}
    scan = SimpleNamespace(render=installed)
    start = now()
    ordinary = scan.render(packet, **options)
    ordinary_time = clock(start)
    with binding(scan, audit, orbit_sheets=False):
        start = now()
        residual = scan.render(packet, **options)
        residual_time = clock(start)
    require_active(audit)
    hashes = {"ordinary": image_hashes(ordinary), "residual_layout": image_hashes(residual)}
    if any(ordinary[name] != residual[name] for name in ORBIT_SHEETS):
        raise ValueError("Residual layout altered an ordinary orbit sheet")
    times = {"ordinary": ordinary_time, "residual_layout": residual_time}
    return dict(hashes=hashes, clocks=times, work=audit, source_scene_sha256=digest,
                saved={key: ordinary_time[key] - residual_time[key] for key in ordinary_time})


def preflight(output):
    from aperture_trial import write
    from exact_named_cairo import control

    _, receipt = control("0316")
    trial = render_pair(ARCHIVED_SCENE, ARCHIVED_SHA)
    expected = receipt["artifacts"]["candidate"]["products"]["images"]
    if trial["hashes"]["ordinary"] != {name: image["sha256"] for name, image in expected.items()}:
        raise ValueError("Preflight did not reproduce the independently archived ordinary charts")
    write(output, trial | {"sources": source_pins()})


def launch(root, preflight_path):
    from aperture_trial import write
    from empty_bootstrap import RELEASE
    from history_risk_route_trial import launch as original_launch
    from portable_orbit_index_trial import local_launcher_tools

    preflight = read(preflight_path)
    require_active(preflight["work"])
    if (preflight["sources"] != source_pins() or preflight["source_scene_sha256"] != ARCHIVED_SHA
            or preflight["saved"]["cpu_s"] <= 0):
        raise ValueError("The original-orbit preflight must pass and demonstrate some faster rendering")
    controls()
    local_launcher_tools()
    renderer = source_digest(source_pins())
    original_launch("0402", root, stock_command=[RELEASE/"venv/bin/python", "-IB", __file__, "worker", "--digest", renderer])
    write(root/"renderer-binding.json", dict(sources=source_pins(), sha256=renderer, control=CONTROL,
                                            preflight_sha256=sha256(preflight_path.read_bytes()).hexdigest()))


def worker(output, expected, *, case="0402", pins=source_pins):
    from empty_bootstrap import clock, now
    from history_cairo_render import binding
    from history_risk_route_trial import exact, worker as original_worker

    active_sources = pins()
    if source_digest(active_sources) != expected:
        raise ValueError("The selected renderer sources changed during launch")
    root = output.parent
    ordinary_ports = exact.exact_ports
    work, timing, scene = {}, {}, []

    @contextmanager
    def renderer(*args, **kwargs):
        from tools import algo08_scan

        with ordinary_ports(*args, **kwargs), binding(algo08_scan, work, orbit_sheets=False):
            candidate = algo08_scan.render

            def observed(packet, **options):
                scene.append((packet, options))
                start = now()
                images = candidate(packet, **options)
                timing.update(clock(start))
                return images

            with patch.object(algo08_scan, "render", observed):
                yield

    with patch.object(exact, "exact_ports", renderer):
        original_worker(case, root)
    from aperture_trial import write

    require_active(work)
    (packet,) = scene
    start = now()
    data = pickle.dumps(packet, protocol=pickle.HIGHEST_PROTOCOL)
    with (root/SCENE).open("xb") as stream:
        stream.write(data)
    digest = sha256(data).hexdigest()
    write(root/"render.json", dict(work=work, render=timing, sources=active_sources, scene_sha256=digest,
                                   scene_capture=clock(start), scene_bytes=len(data)))


def replay(root):
    from aperture_trial import write

    render = read(root/"render.json")
    if render["sources"] != source_pins():
        raise ValueError("Replay must use the frozen candidate renderer")
    write(root/"replay.json", render_pair(root/SCENE, render["scene_sha256"]))


def score(root):
    sys.path[:0] = [str(ROOT/"src"), str(ROOT)]
    from aperture_trial import write
    from direct_residual_figures_trial import pixels
    from empty_bootstrap import checked
    from exact_named_cairo_media import verify_publication
    from held_adaptive_0160_score import verified
    from history_risk_cairo_physical import clean
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from named_weak_visual import registered_orbits
    from io import BytesIO
    from PIL import Image

    control, request = controls()
    elapsed = read(root/"clock.json")
    old = verified(PRIOR/"candidate", control["clock.json"], "worker.json", request)
    new = verified(root/"candidate", elapsed, "worker.json", request)
    marks, sidecars = verify_publication(old, new, PRIOR/"candidate", root/"candidate")
    if (read(root/"binding.json")["input"] != control["binding.json"]["input"]
            or clean(read(root/"risk-route.json")) != clean(read(PRIOR/"risk-route.json"))
            or old["trace"]["machine"] != new["trace"]["machine"]
            or old["trace"]["selected_roles"] != new["trace"]["selected_roles"]):
        raise ValueError("Only the image renderer may differ")
    before, after = (arm["products"]["images"] for arm in (old, new))
    cairo = json.loads(checked(ALL_CAIRO, ALL_CAIRO_SHA))["media"]
    archival = {name: (before[name] if name in ORBIT_SHEETS else cairo[name]["cairo"]) for name in before}
    if media_identity(after) != media_identity(archival):
        raise ValueError("The four original orbit and four qualified faster images must each match")
    worker, replayed, renderer = (read(root/f"{name}.json") for name in ("render", "replay", "renderer-binding"))
    require_active(worker["work"])
    require_active(replayed["work"])
    pins = source_pins()
    if (renderer["sources"] != worker["sources"]
            or renderer["sources"] not in (pins, pins | {Path(__file__).name: TIMED_DRIVER},
                                          pins | {Path(__file__).name: PREVIOUS_DRIVER})
            or renderer["sha256"] != source_digest(renderer["sources"]) or replayed["source_scene_sha256"] != worker["scene_sha256"]
            or any(replayed["hashes"][mode] != {name: item["sha256"] for name, item in figures.items()}
                   for mode, figures in (("ordinary", before), ("residual_layout", after)))):
        raise ValueError("The isolated render times must reproduce all of the official images in each mode")
    ports = read(root/"candidate/ports.json")
    if tuple(ports["png"][k] for k in ("verified", "reused", "fallbacks")) != (8, 8, 0):
        raise ValueError("The active complete publication must verify eight genuine images")
    stores = [FastStandardAnalysisStore(folder/"candidate") for folder in (PRIOR, root)]
    run = new["worker"]["receipt"]["run_id"]
    media = {}
    for name in before:
        images = [store.artifact(run, name, items[name]["sha256"]) for store, items in zip(stores, (before, after), strict=True)]
        media[name] = dict(pixels(*images), images=[before[name], after[name]])
        if name in ORBIT_SHEETS:
            with Image.open(BytesIO(images[0])) as a, Image.open(BytesIO(images[1])) as b:
                media[name]["orbit_registration"] = registered_orbits(a.convert("RGB"), b.convert("RGB"))
    write(root/"result.json", dict(clocks={"ordinary": old["clock"], "residual_layout": elapsed},
          renderer_binding=renderer, admission=read(root/"route-binding.json")["preflight"],
          ordinary_admission=control["route-binding.json"]["preflight"], render=worker, replay=replayed,
          owner_counts={name: len(rows) for name, rows in new["rows"].items()}, scientific=control["result.json"]["scientific"],
          publication_checks=marks, sidecars=sidecars, terminal=new["terminal"], media=media,
          solve={mode: arm["trace"]["solve"] for mode, arm in (("ordinary", old), ("residual_layout", new))},
          verified_png=ports["png"], waveform_reads=0, backing_reads=0))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "launch", "worker", "replay", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--digest")
    args = parser.parse_args()
    if args.action == "launch":
        launch(args.root, args.preflight)
    elif args.action == "worker":
        worker(args.root, args.digest)
    else:
        {"preflight": preflight, "replay": replay, "score": score}[args.action](args.root)
