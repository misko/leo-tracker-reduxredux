"""Observe the real residual-layout render scene in one exact named raw child."""

from contextlib import contextmanager
import json
from pathlib import Path
import pickle
from unittest.mock import patch

import exact_named_raw as route
import history_cairo_render


def run(command):
    from empty_bootstrap import clock, now

    args = route.parser().parse_args(command)
    if not (args.cairo_residual_layout and args.history_risk_route and args.visit_frame_custody and args.portable_orbit_index):
        raise ValueError("Expected the frozen combined candidate")
    original = history_cairo_render.binding
    observed = []

    @contextmanager
    def capture(scan, audit, *, orbit_sheets):
        if orbit_sheets:
            raise ValueError("Keep the four original Matplotlib orbit sheets")
        with original(scan, audit, orbit_sheets=False):
            draw = scan.render

            def render(packet, **options):
                observed.append((packet, options))
                return draw(packet, **options)

            with patch.object(scan, "render", render):
                yield

    with patch.object(history_cairo_render, "binding", capture):
        terminal = route.run(args)
    if terminal["decision"] != "complete":
        raise ValueError("Expected the compatible new recording's complete publication")
    (scene,) = observed
    if scene[1]["title"] != args.recording.name:
        raise ValueError("The rendered title must identify the new recording")
    started = now()
    location = args.output/"render-scene.pickle"
    with location.open("xb") as file:
        pickle.dump(scene, file, protocol=pickle.HIGHEST_PROTOCOL)
    result = dict(clock=clock(started), scene_bytes=location.stat().st_size, title=scene[1]["title"])
    with (args.output/"render-scene.json").open("x") as file:
        json.dump(result, file)


if __name__ == "__main__":
    import sys

    run(sys.argv[1:])
