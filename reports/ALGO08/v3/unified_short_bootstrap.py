"""Acquire independently signed 20/12 ms stereo, then publish in one process."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
LAYOUT_SHA256 = "0be5c8a2f90d36691d1bb20a1e3dee0fe17eae7a70b66b732a560cf0257c88aa"


@contextmanager
def receiver_import(name, symbols):
    """Load only the pinned native ABI and row constructors during acquisition."""
    if name in sys.modules:
        raise ValueError("Receiver-first acquisition requires a fresh native binding")
    module = ModuleType(name)
    for key in ("Native", "Factor", "_probe", "factor_candidate"):
        setattr(module, key, symbols[key])
    # The reviewed receiver imports these names dynamically. Restore just its
    # module entry so other first-use imports survive the acquisition.
    sys.modules[name] = module
    try:
        yield
    finally:
        del sys.modules[name]


class Handoff:
    def __init__(self, session, inventory, receiver, native):
        self.session, self.inventory, self.receiver, self.native = session, inventory, receiver, native
        self.calls = 0

    @contextmanager
    def install(self, scan):
        def acquire(session, digest, *_):
            if self.calls or (session, digest) != (self.session, self.inventory):
                raise ValueError("Expected one handoff bound to the authenticated raw acquisition")
            self.calls += 1
            # The installed scanner checks the real anchor DSO before this
            # port runs and binds its subsequent native checks to the recipe.
            scan.PINS["cancellation-factors.so"] = self.receiver
            return self.native

        with patch.dict(scan.PINS, {}), patch.object(scan, "acquire", acquire):
            yield


def withhold(scan, args, offer, assets, handoff, reason, *, graph_proof=None):
    if reason not in ("no_active_curvature", "no valid receiver windows in the sealed recording"):
        raise ValueError("Expected a verified empty receiver decision")
    if any(probe["candidates"] for probe in handoff.native["source"]["probes"]):
        from leo.contracts.digests import canonical_digest

        if (graph_proof is None or graph_proof.get("proven") is not True
                or reason != "no_active_curvature" or graph_proof["native_sha256"] != canonical_digest(handoff.native)):
            raise ValueError("An authenticated factor requires the ordinary numerical path unless its graph is proven empty")
    scan.TleArchiveReader = lambda path: path
    scan.solve = lambda *_: (dict(status="withheld", reason=reason,
                                 arms={name: {"latlon": None} for name in ("c0", "fitted_c")}), None, "stock")
    args.output.mkdir()
    with handoff.install(scan):
        return scan.analyze(args.recording, args.output, assets, args.archive, offer)


@contextmanager
def layout_renderer(scan, enabled, audit):
    if not enabled:
        yield
        return

    from empty_bootstrap import clock, now
    from one_pass_web_png import render

    if Path(render.__code__.co_filename).resolve() != HERE / "one_pass_web_png.py":
        raise ValueError("Expected the reviewed one-pass publication renderer")
    installed = scan.render

    def opted_in(packet, **options):
        start = now()
        images, detail = render(installed, packet, enabled=True, **options)
        audit.update(work=detail, render=clock(start))
        return images

    with patch.object(scan, "render", opted_in):
        yield


def publish_active(args, publication, specification, handoff, layout_audit, *, graph_audit=None):
    from exact_graph_execution import graph_execution
    from full_short_run import geographic_projection
    import joint_publication
    from regional_probe_block_binding import guarded_projection

    options = SimpleNamespace(**vars(args), saved=None, saved_digest=None,
                              optimized_full_catalogue=True, verify_images=True, skip_empty_proof=True)

    def projection():
        return guarded_projection(args.geographic_library, args.regional_track_library,
                                  args.frontier_block_library, geographic_projection)

    @contextmanager
    def active_publication(scan):
        # The installed lossless renderer is bound before the analyze hook.
        with (handoff.install(scan), layout_renderer(scan, args.one_pass_web_png, layout_audit),
              graph_execution(enabled=getattr(args, "exact_graph_reuse", False), audit=graph_audit)):
            yield

    # Bootstrap already installed the release's lazy package facades. The
    # normal analyze/raw-context boundary consumes the in-memory packet once.
    with patch.object(joint_publication, "configuration", return_value=(publication, dict(specification, startup="stock"))):
        result = joint_publication.run(options, raw_context=active_publication, early_regional=True,
                                       keep_selected_rows=True, geographic_projector=projection,
                                       reuse_cold_rows=True, reuse_grid_phase_states=True)
    return result["receipt"], result


def run(args):
    import empty_bootstrap as staged

    started = staged.now()
    if args.output.exists() or not args.output.parent.is_dir():
        raise ValueError("Choose a new local publication directory beneath an existing parent")
    launcher, specification, sources, publication, checks = staged.load_runtime()
    from combined_frontier_run import BLOCK_SHA, PREFETCH_FILES, load_prefetch
    from full_short_raw import observe_acquisition
    from full_short_run import GEOGRAPHIC_SHA, RECIPE_SHA, SHORT_SHA, TRACK_SCORES_SHA, checked_recipe
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.digests import canonical_digest
    from mixed_aperture_receiver import MixedApertureDetector
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes
    from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer

    inputs = ((args.short_binary, SHORT_SHA), (args.geographic_library, GEOGRAPHIC_SHA),
              (args.regional_track_library, TRACK_SCORES_SHA), (args.frontier_block_library, BLOCK_SHA))
    for path, pin in inputs:
        staged.checked(path, pin)
    if args.one_pass_web_png:
        staged.checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    recipe = checked_recipe()
    mixer = MixedApertureDetector(args.short_binary, SHORT_SHA, full_coverage=True)
    scan = staged.staged_scanner(sources, detector=mixer.detector)
    symbols = staged.receiver_symbols(sources)
    native_import = staged.RECEIVER.removesuffix(".py").replace("/", ".")
    offer_bytes = args.region.read_bytes()
    offer = scan.Algo08Region.parse(json.loads(offer_bytes))
    phases = {"installed_source_checks": checks, "receiver_ready_from_entry": staged.clock(started)}
    archive = args.archive.resolve(strict=True)
    if not archive.is_dir():
        raise ValueError("Expected the causal archive directory")
    scope = staged.now()
    audit, layout_audit = {}, {}
    graph_audit = {} if args.exact_graph_reuse else None
    with TemporaryDirectory() as temporary:
        assets = Path(temporary)
        anchor = specification["detector_sha256"]
        if anchor != recipe["installed_sha256"]:
            raise ValueError("Mixed-aperture anchors differ from the installed receiver")
        for name in (*scan.PINS, "native", "projector.so"):
            source = Path(specification["detector"]) if name == "cancellation-factors.so" else staged.RELEASE / "assets" / name
            (assets / name).symlink_to(source)
        scan.PINS["cancellation-factors.so"] = anchor
        for name, pin in scan.PINS.items():
            staged.checked(assets / name, pin)
        paired = specification["paired_sha256"]
        library = assets / "paired-sha256.so"
        library.write_bytes(staged.checked(Path(paired["library"]), paired["sha256"]))
        publication._checked_member_lookahead(specification)
        fetch = load_prefetch()
        session, inventory_digest, inventory = scan.FastScanStore(args.output).inventory(args.recording, verify_windows=False)
        phases["asset_and_inventory_checks"] = staged.clock(scope)
        scope = staged.now()
        with (receiver_import(native_import, symbols), observe_acquisition(scan, mixer, RECIPE_SHA, audit),
              compressed_input_buffer(), paired_decoded_hashes(library), fetch() as prefetch):
            native = scan.acquire(session, inventory_digest, inventory, assets)
        staged.bind_native(native, session, inventory_digest, RECIPE_SHA)
        phases["authenticated_raw_acquisition"] = staged.clock(scope)
        if args.region.read_bytes() != offer_bytes:
            raise ValueError("The offered region changed during acquisition")
        scope = staged.now()
        reason = staged.empty_reason(native, frequency_evidence)
        graph_proof = None
        if reason is None and args.prove_empty_graph:
            from short_graph_guard import prove

            graph_proof = prove(native, assets)
            if graph_proof["proven"]:
                reason = "no_active_curvature"
        before = [name for name in staged.SCIENTIFIC_IMPORTS if name in sys.modules]
        if before:
            raise ValueError(f"Scientific imports crossed the receiver-first boundary: {before}")
        handoff = Handoff(session, inventory_digest, RECIPE_SHA, native)
        if reason is None:
            terminal, research = publish_active(args, publication, specification, handoff, layout_audit, graph_audit=graph_audit)
            route = "optimized_installed_graph"
        else:
            staged.check_inert_solver_assets(assets)
            terminal = withhold(scan, args, offer, assets, handoff, reason, graph_proof=graph_proof)
            research = None
            route = ("authenticated_zero_selected_factors" if graph_proof is None
                     else "authenticated_installed_graph_ineligible")
        phases["decision_and_publication"] = staged.clock(scope)
    after = [name for name in staged.SCIENTIFIC_IMPORTS if name in sys.modules]
    if handoff.calls != 1 or reason is not None and after:
        raise ValueError("The authenticated packet did not reach the required publication route once")
    (published,) = (args.output / "fast-scan-automatic-work").glob("*/detections.json")
    native_sha = canonical_digest(native)
    if "sha256:" + sha256(published.read_bytes()).hexdigest() != native_sha or terminal["region"] != offer.document():
        raise ValueError("Immutable publication differs from the acquired packet or offered region")
    dependencies = ("empty_bootstrap.py", "full_short_raw.py", "full_short_run.py", "combined_frontier_run.py",
                    "regional_probe_block_binding.py", "unified_short_bootstrap.py")
    result = dict(schema_version=1, implementation="unified signed raw research receiver and solver",
                  route=route, requested_offer_sha256=sha256(offer_bytes).hexdigest(), archive_root=str(archive),
                  frozen_specification="sha256:"+launcher["FINGERPRINT"], receiver_recipe=recipe,
                  detector_recipe_sha256="sha256:"+RECIPE_SHA, stock_launcher_sha256=staged.BASELINE_PIN,
                  native_sha256=native_sha, clock_anchor=native["clock_anchor"],
                  causal_cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"], receipt=terminal,
                  source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in dependencies},
                  installed_acquisition_sources=staged.EXTRA_SOURCES,
                  solver_source_sha256=None if research is None else research["source_sha256"],
                  graph_proof=graph_proof,
                  exact_graph_reuse=dict(requested=args.exact_graph_reuse, executed=graph_audit or None),
                  one_pass_web_png=dict(enabled=args.one_pass_web_png,
                                        source_sha256=LAYOUT_SHA256 if args.one_pass_web_png else None, **layout_audit),
                  solver_recipe=dict(graph="installed", block_sha256=BLOCK_SHA, scalar_track_sha256=TRACK_SCORES_SHA,
                                     geographic_sha256=GEOGRAPHIC_SHA, reuse_cold_rows=True,
                                     reuse_grid_phase_states=True, skip_empty_proof=True),
                  prefetch_sources=PREFETCH_FILES, prefetch=asdict(prefetch), raw_acquisitions=1,
                  verified_handoffs=handoff.calls, receiver_audit=audit, phases=phases,
                  scientific_imports_before=before, scientific_imports_after=after,
                  total_before_receipt=staged.clock(started))
    with (args.output / "unified-short-bootstrap.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return terminal


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "output", "short-binary", "geographic-library",
                 "regional-track-library", "frontier-block-library"):
        parser.add_argument("--"+name, type=Path, required=True)
    parser.add_argument("--prove-empty-graph", action="store_true",
                        help="Use the pinned minimum support proof before loading the numerical solver")
    parser.add_argument("--one-pass-web-png", action="store_true",
                        help="Use the reviewed explicit layout on the installed renderer when supported")
    parser.add_argument("--exact-graph-reuse", action="store_true",
                        help="Use reviewed ordered graph batches and exact best-piece reuse in active lanes")
    print(json.dumps(run(parser.parse_args()), allow_nan=False))
