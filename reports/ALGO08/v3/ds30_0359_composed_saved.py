"""Compose only the validated predictive, ordinary Agg and PNG changes."""

import argparse
from contextlib import ExitStack, contextmanager
import json
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from ds30_0359_cairo_saved import JOB_PIN, READY, READY_PIN, digest, launch, read

PROTOCOL = HERE / "ds30-0359-composed-saved-protocol.md"
PAIRED = Path("/dev/shm/leo-v3-0359-predictive-grid-result01/result.json")
PAIRED_PIN = "4404ceb1d587afee549978f09411c7a90810311384a873865ea1cab5b2a4c85c"


def qualification():
    from empty_bootstrap import checked

    paired = json.loads(checked(PAIRED, PAIRED_PIN))
    if not paired["qualified"] or not all(paired["checks"].values()):
        raise ValueError("The matched grid and exact media must qualify before a clean comparison")
    return paired


def sources():
    from empty_bootstrap import checked
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA

    qualification()
    checked(PNG_LIBRARY, PNG_SHA)
    names = (Path(__file__).name, PROTOCOL.name, "fixed_orbit_artists.py", "ordinary_orbit_reuse.py",
             "optimized_grid.py", "grid_predictive_reduction.py", "history_cairo_render.py", "verified_rgba.py",
             "verified_rgba_rows.c", "verified_png_reads.py", "integrated_original_entry.py")
    return {"composed_sources": {str((HERE / name).relative_to(ROOT)): digest(HERE / name) for name in names},
            "paired_result_sha256": PAIRED_PIN}


@contextmanager
def exact_orbits(ordinary, audit, stats):
    from empty_bootstrap import checked
    from fixed_orbit_artists import fixed_artists
    from leo.presentation import orbit_plot
    from matplotlib.backends.backend_agg import FigureCanvasAgg as Canvas
    from ordinary_orbit_reuse import RestoreAfterCopy, SOURCES
    from tools.pipeline_eval.variants.experimental import raster_layout, shared_orbit_figures as shared

    for module in (orbit_plot, raster_layout, shared):
        path = Path(module.__file__)
        checked(path, SOURCES[path.name])
    if raster_layout.render_shared is not shared.render_shared:
        raise ValueError("The preserved Agg route must use the reviewed shared orbit renderer")
    copy, restore = Canvas.copy_from_bbox, Canvas.restore_region
    with ordinary(audit):
        render = raster_layout.render_shared

        def compose(lanes, **options):
            with fixed_artists(lanes, **options, raster_layout=raster_layout) as fixed:
                if fixed is None:
                    stats["ordinary_fallback"] = "unsupported fixed-limit figure"
                    return render(lanes, **options)
                state, skipped = RestoreAfterCopy(), 0

                def save(canvas, bounds):
                    pixels = copy(canvas, bounds)
                    state.copied(canvas, bounds, pixels)
                    return pixels

                def recover(canvas, region, *args, **kwargs):
                    nonlocal skipped
                    if state.redundant(canvas, region) and not args and not kwargs:
                        skipped += 1
                        return None
                    return restore(canvas, region, *args, **kwargs)

                with patch.object(Canvas, "copy_from_bbox", save), patch.object(Canvas, "restore_region", recover):
                    products = render(lanes, **options)
                stats.update(fixed | {"first_restores_elided": skipped})
                return products

        with patch.object(raster_layout, "render_shared", compose):
            yield


def worker(root):
    import empty_bootstrap as boot
    from aperture_trial import write
    import history_cairo_render as layout
    from integrated_original_entry import verification_factory
    from reports.ALGO08.v3 import ds30_0163_combined as original
    import verified_png_reads as png

    book = read(root / "admission.json")
    if book["paired_result_sha256"] != PAIRED_PIN or book["protocol_sha256"] != digest(PROTOCOL):
        raise ValueError("The clean candidate lacks its verified paired-grid prerequisite")
    for path, value in book["composed_sources"].items():
        if digest(ROOT / path) != value:
            raise ValueError(f"The composed source changed: {path}")
    stats, native, audit = {}, {}, []
    load, ordinary = boot.load_runtime, layout.ordinary_orbits

    with ExitStack() as stack:
        def enabled():
            runtime = load()
            from optimized_grid import reduced_grid

            audit.append(stack.enter_context(reduced_grid()))
            return runtime

        stack.enter_context(patch.object(boot, "load_runtime", enabled))
        stack.enter_context(patch.object(layout, "ordinary_orbits", lambda counters: exact_orbits(ordinary, counters, stats)))
        stack.enter_context(patch.object(png, "VerifiedPngReads", verification_factory(png.VerifiedPngReads, native)))
        original.worker(root, job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    predictive, = audit
    write(root / "composition.json", dict(predictive=dict(predictive), native_png=native, agg=stats))


def probe():
    from integrated_original_entry import PNG_LIBRARY, PNG_SHA
    from reports.ALGO08.v3 import ds30_0163_combined as original
    from verified_rgba import RgbaEvidence

    result = original.probe(job_root=READY, admission_pin=READY_PIN, job_pin=JOB_PIN)
    print(json.dumps(result | {"composed_ready": RgbaEvidence(PNG_LIBRARY, PNG_SHA, None, {}).ready}))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "probe"))
    cli.add_argument("root", type=Path, nargs="?")
    args = cli.parse_args()
    if args.action == "probe":
        probe()
    elif args.action == "worker":
        worker(args.root)
    else:
        launch(args.root, entry=Path(__file__), extra_sources=sources, protocol=PROTOCOL, probe_marker="composed_ready")
