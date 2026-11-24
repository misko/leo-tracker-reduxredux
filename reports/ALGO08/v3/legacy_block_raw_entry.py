"""Run the exact portable history-risk route with optional original block maps."""

import sys
from contextlib import ExitStack, contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))


def parser():
    from exact_named_raw import parser as exact_parser

    cli = exact_parser()
    cli.add_argument("--legacy-map-custody", type=Path)
    cli.add_argument("--legacy-map-custody-sha256")
    cli.add_argument("--legacy-map-library", type=Path)
    cli.add_argument("--legacy-map-library-sha256")
    return cli


def run(args):
    import empty_bootstrap as boot
    import exact_named_raw as route
    import history_cairo_render

    if (
        not args.history_risk_route
        or not args.cairo_residual_layout
        or not args.portable_orbit_index
        or args.cairo_six_sheets
        or args.visit_frame_custody
        or args.strict_packed_eight
    ):
        raise ValueError(
            "Expected portable history-risk and ordinary orbit sheets on the original recording"
        )
    fields = (
        args.legacy_map_custody,
        args.legacy_map_custody_sha256,
        args.legacy_map_library,
        args.legacy_map_library_sha256,
    )
    audit = None
    original = history_cairo_render.binding

    @contextmanager
    def checked_renderer(scan, rendered, *, orbit_sheets):
        if orbit_sheets:
            raise ValueError("Use the standard four orbit sheets in both arms")
        with original(scan, rendered, orbit_sheets=False):
            draw = scan.render

            def render(packet, **options):
                title = options["title"]
                if title != args.recording.name:
                    raise ValueError("The rendered title changed its original recording")
                images = draw(packet, **options)
                rendered["original_recording_title"] = title
                return images

            with patch.object(scan, "render", render):
                yield

    with ExitStack() as stack, patch.object(history_cairo_render, "binding", checked_renderer):
        if any(fields):
            if not all(fields):
                raise ValueError(
                    "Detached custody and native decoder require their external SHA-256 pins"
                )
            started = boot.now()
            with patch.object(sys, "path", [*sys.path, str(ROOT)]):
                from reports.ALGO08.v3 import legacy_block_input, legacy_block_seek
            custody, pin, library, lib_pin = fields
            plan = legacy_block_input.load_custody(custody, pin)
            legacy_block_input.checked_file(library, lib_pin, 2_000_000)
            audit = dict(
                custody_sha256=pin,
                binary_sha256=lib_pin,
                source_sha256={
                    Path(module.__file__).name: "sha256:"
                    + sha256(Path(module.__file__).read_bytes()).hexdigest()
                    for module in (legacy_block_input, legacy_block_seek)
                },
            )
            stack.enter_context(
                legacy_block_input.binding(
                    boot, plan, custody.parent, legacy_block_seek.load(library), audit
                )
            )
            audit["setup"] = boot.clock(started)
        terminal = route.run(args)
    if audit is not None:
        route.write(args.output / "legacy-map-acquisition.json", audit, scientific=True)
    return terminal


if __name__ == "__main__":
    run(parser().parse_args())
