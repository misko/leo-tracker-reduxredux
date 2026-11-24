"""Substitute only the six-sheet Cairo renderer in the routed saved 0402 worker."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
PRIOR = Path("/dev/shm/leo-v3-history-risk-0402-pair01-routed")
CONTROL = {
    "result.json": "7c6fb541754cff8d34c7e78b7946b5904926e2ed4dce27821f7cf9879873bbbc",
    "binding.json": "dbe3c180c6e7b8cb9c1a86ab8d74039203c1d75c9e0d63c497b2ce9d68eb2a20",
    "clock.json": "e4f2e82125515048e6de7bfa4f027f514c33c727db1248c0c69552ce7152d9fd",
    "route-binding.json": "c6fceb45ea818934bfb5173c62e388471f2abcffb3b5a08dd5d3ac6074f0be0b",
}
ORBIT_SHEETS = ("ch1-4-all", "ch1-4-unassociated", "ch5-8-all", "ch5-8-unassociated")
DISPATCHER = "history_risk_route_trial.py"
ORIGINAL_DISPATCHER = "0e47a870b083e2eea23d86a0412c59d399d5224967cd4b5fd246ea00e18c4f92"
CURRENT_DISPATCHER = "df0f8043c00387a2933bd2d8bf7fad812b9020c58507cc76863c05f8d74e02b2"


def read(path):
    return json.loads(path.read_bytes())


def source_pins():
    from history_cairo_render import SOURCES

    names = (*SOURCES, Path(__file__).name, "history-risk-cairo-0402-protocol.md", "history_cairo_artists.py")
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in names}


def renderer_pin():
    return sha256(json.dumps(source_pins(), sort_keys=True).encode()).hexdigest()


def controls():
    from empty_bootstrap import checked
    from history_risk_route_trial import request_binding, sources

    old = {name: json.loads(checked(PRIOR/name, pin)) for name, pin in CONTROL.items()}
    entry, request = request_binding("0402")
    result = old["result.json"]
    old_sources = old["route-binding.json"]["sources"]
    # da2358879 added the 0169 input, admission and offline scoring. The
    # worker is unchanged and the 0402 branches use the same inputs and ports.
    if (entry != old["binding.json"]["input"] or old_sources.get(DISPATCHER) != ORIGINAL_DISPATCHER
            or sources("0402") != old_sources | {DISPATCHER: CURRENT_DISPATCHER}
            or old["clock.json"] != result["clock"] or old["clock.json"]["exit_code"]
            or result["route"]["route"] != "lean" or len(result["published"]["products"]["images"]) != 8):
        raise ValueError("The comparison needs the exact qualified ordinary saved route")
    return old, request


def launch(root):
    from empty_bootstrap import RELEASE
    from history_risk_weak_physical import deny_original
    from portable_orbit_index_trial import local_launcher_tools

    sys.addaudithook(deny_original)
    local_launcher_tools()
    from history_risk_route_trial import launch as original_launch
    from aperture_trial import write

    controls()
    renderer = renderer_pin()
    original_launch("0402", root, stock_command=[RELEASE/"venv/bin/python", "-IB", __file__, "worker", renderer])
    write(root/"renderer-binding.json", dict(sources=source_pins(), sha256=renderer, control=CONTROL, scope="saved 0402"))


def worker(output, expected):
    from empty_bootstrap import clock, now
    from history_risk_weak_physical import deny_original
    from history_cairo_artists import capture
    from history_cairo_render import binding
    from history_risk_route_trial import exact, worker as original_worker

    sys.addaudithook(deny_original)
    if renderer_pin() != expected:
        raise ValueError("The renderer or scoring recipe differs from the frozen launch")
    root = output.parent
    ordinary_ports = exact.exact_ports
    work, artists, timing = {}, {}, {}

    @contextmanager
    def cairos(*args, **kwargs):
        from tools import algo08_scan

        with ordinary_ports(*args, **kwargs), binding(algo08_scan, work):
            native_render = algo08_scan.render

            def observed(packet, **options):
                started = now()
                with capture(artists, True):
                    images = native_render(packet, **options)
                timing.update(clock(started))
                return images

            with patch.object(algo08_scan, "render", observed):
                yield

    with patch.object(exact, "exact_ports", cairos):
        original_worker("0402", root)
    from aperture_trial import write

    write(root/"render.json", dict(work=work, render=timing, artists=artists, sources=source_pins()))


def failed_layers(registration, threshold=.98):
    return [dict(sheet=name, panel=i+1, layer=kind, fraction=layer["fraction"])
            for name, sheet in registration.items() for i, row in enumerate(sheet["rows"])
            for kind, layer in row.items() if layer["fraction"] and min(layer["fraction"]) < threshold]


def score(root):
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    sys.path[:0] = [str(ROOT/"src"), str(ROOT)]
    from aperture_trial import write
    from PIL import Image
    from direct_residual_figures_trial import pixels
    from exact_named_cairo_media import act
    from held_adaptive_0160_score import verified
    from history_risk_cairo_physical import clean
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    from named_weak_visual import registered_orbits
    from publication_media_checks import verify_position_sidecars

    prior, request = controls()
    clock = read(root/"clock.json")
    before = verified(PRIOR/"candidate", prior["clock.json"], "worker.json", request)
    after = verified(root/"candidate", clock, "worker.json", request)
    old, new = (read(folder/"risk-route.json") for folder in (PRIOR, root))
    if (read(root/"binding.json")["input"] != prior["binding.json"]["input"] or clean(old) != clean(new)
            or before["terminal"] != after["terminal"] or before["rows"] != after["rows"]
            or before["science"]["arms"] != after["science"]["arms"]
            or before["trace"]["selected_roles"] != after["trace"]["selected_roles"]
            or before["trace"]["machine"] != after["trace"]["machine"]
            or any(run["sample"]["evaluated_points"] != 179 or not run["sample"]["complete"] for run in (before, after))):
        raise ValueError("Only renderer work may change the original signed study")
    media = read(root/"render.json")
    act(media["work"])
    if (read(root/"renderer-binding.json")["sha256"] != renderer_pin() or media["sources"] != source_pins()
            or tuple(media["work"].get(x) for x in ("position_figures", "track_figures")) != (1, 1)):
        raise ValueError("All six Cairo sheets and both explicit-layout products must execute")
    ports = read(root/"candidate/ports.json")
    if ports["png"]["verified"] != 8 or ports["png"]["reused"] != 8 or ports["png"]["fallbacks"]:
        raise ValueError("All eight published PNGs must pay the same verified read")
    run = after["worker"]["receipt"]["run_id"]
    old, new = (report["products"]["images"] for report in (before, after))
    folders = (PRIOR/"candidate", root/"candidate")
    sidecars = verify_position_sidecars(*folders, run, old, new)
    stores = [FastStandardAnalysisStore(folder) for folder in folders]
    images, orbit = {}, {}
    for name in old:
        data = [store.artifact(run, name, record[name]["sha256"]) for store, record in zip(stores, (old, new), strict=True)]
        images[name] = pixels(*data) | {"ordinary": old[name], "cairo": new[name]}
        if name in ORBIT_SHEETS:
            with Image.open(BytesIO(data[0])) as a, Image.open(BytesIO(data[1])) as b:
                orbit[name] = registered_orbits(a.convert("RGB"), b.convert("RGB"), require_match=False)
    failed = failed_layers(orbit)
    ordinary_clock = before["clock"]
    ceiling = {key: before["trace"][f"publication_{key}"]-before["trace"]["solve"][key] for key in ("elapsed_s", "cpu_s")}
    write(root/"result.json", dict(case="DS30-0402", clocks={"ordinary":ordinary_clock,"cairo":clock},
        saved_saving={key: ordinary_clock[key]-clock[key] for key in ("elapsed_s", "cpu_s")}, ordinary_render_ceiling=ceiling,
        cairo=media, named_route=new, ordinary_admission=prior["route-binding.json"]["preflight"],
        cairo_admission=read(root/"route-binding.json")["preflight"], solve={"ordinary":before["trace"]["solve"],"cairo":after["trace"]["solve"]},
        position_reference=prior["result.json"]["scientific"], owner_counts={arm: len(rows) for arm, rows in after["rows"].items()},
        terminal=after["terminal"], sidecars=sidecars, media=images, registration=orbit, failed_layers=failed,
        visual_pass=not failed, waveform_opens=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    for name in ("launch", "score"):
        commands.add_parser(name).add_argument("root", type=Path)
    child = commands.add_parser("worker")
    child.add_argument("expected")
    child.add_argument("root", type=Path)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.root, args.expected)
    else:
        {"launch": launch, "score": score}[args.action](args.root)
