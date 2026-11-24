"""Acquire independently signed 20/12 ms stereo, then publish in one process."""

import argparse
from contextlib import ExitStack, contextmanager, nullcontext
from dataclasses import asdict
from functools import partial
from hashlib import sha256
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
LAYOUT_SHA256 = "0be5c8a2f90d36691d1bb20a1e3dee0fe17eae7a70b66b732a560cf0257c88aa"
ADAPTIVE_MAP_SOURCES = ("live_adaptive_grid_entry.py", "live_adaptive_grid.py", "adaptive_grid_screen.py")


@contextmanager
def adaptive_map_layout(output):
    # The isolated raw entry only exposes the report directory. The adapter
    # imports the review modules by repository-qualified names.
    with patch.object(sys, "path", [*sys.path, str(HERE.parents[2])]):
        from reports.ALGO08.v3.live_adaptive_grid_entry import research_layout

        with research_layout(output):
            yield


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
def layout_renderer(scan, enabled, audit, *, direct_residuals=False, direct_orbits=False):
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
        orbit_details = {}
        orbit_context = nullcontext()
        if direct_orbits:
            from direct_orbit_entry import native_orbits

            orbit_context = native_orbits(installed, orbit_details)
        with orbit_context:
            if direct_residuals:
                from direct_residual_entry import render as render_residuals

                images, detail = render_residuals(installed, packet, **options)
            else:
                images, detail = render(installed, packet, enabled=True, **options)
        audit.update(work=detail | orbit_details, render=clock(start))
        return images

    with patch.object(scan, "render", opted_in):
        yield


def publish_active(args, publication, specification, handoff, layout_audit, *, graph_audit=None, png_read_audit=None,
                   detector_import_audit=None, no_active_curvature_sha256=None):
    from exact_graph_execution import graph_execution
    from full_short_run import geographic_projection
    import joint_publication
    from regional_probe_block_binding import guarded_projection

    options = SimpleNamespace(**vars(args), saved=None, saved_digest=None,
                              optimized_full_catalogue=True, verify_images=True, skip_empty_proof=True)
    captured = None
    if getattr(args, "reuse_verified_png_reads", False):
        from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
        from verified_png_reads import VerifiedPngReads

        captured = VerifiedPngReads(args.output, joint_publication.figure_evidence,
                                    png_read_audit if png_read_audit is not None else {})
    grid_library = getattr(args, "grid_feature_projection_library", None)
    grid_audit = {}
    direct_layout = {"direct_residuals": True} if getattr(args, "direct_residual_figures", False) else {}
    if getattr(args, "direct_orbit_figures", False):
        direct_layout["direct_orbits"] = True
    if direct_layout and not args.one_pass_web_png:
        raise ValueError("Direct figure rendering requires the explicit one-pass layout")
    forecast_audit = None
    if getattr(args, "exact_phase_forecast", False):
        forecast_audit = dict(requested=True, executions=[])

    def phase_forecast():
        from exact_phase_forecast import active_forecast

        return active_forecast(forecast_audit)

    def projection():
        return guarded_projection(args.geographic_library, args.regional_track_library,
                                  args.frontier_block_library, geographic_projection)

    @contextmanager
    def active_publication(scan):
        # The installed lossless renderer is bound before the analyze hook.
        with ExitStack() as stack:
            stack.enter_context(handoff.install(scan))
            stack.enter_context(layout_renderer(scan, args.one_pass_web_png, layout_audit, **direct_layout))
            stack.enter_context(graph_execution(enabled=getattr(args, "exact_graph_reuse", False), audit=graph_audit))
            if captured is not None:
                stack.enter_context(captured.capture(FastStandardAnalysisStore))
            if grid_library is not None:
                from grid_feature_projection import active_projection

                stack.enter_context(active_projection(grid_library, grid_audit))
            yield

    # Bootstrap already installed the release's lazy package facades. The
    # normal analyze/raw-context boundary consumes the in-memory packet once.
    with ExitStack() as scope:
        survivor_witness = None
        if getattr(args, "named_survivor_finish", False):
            from isolated_salvage import binding as isolated_families
            from named_survivor_fit import binding as original_final_fit

            survivor_witness = {}
            scope.enter_context(isolated_families())
            scope.enter_context(original_final_fit(survivor_witness))
        scope.enter_context(patch.object(joint_publication, "configuration", return_value=(publication, dict(specification, startup="stock"))))
        if captured is not None:
            scope.enter_context(patch.object(joint_publication, "artifacts", partial(joint_publication.artifacts, verified_read=captured.read)))
        if getattr(args, "lazy_scanner_detector", False):
            from lazy_scanner_detector import defer_detector

            scope.enter_context(defer_detector(enabled=True, audit=detector_import_audit if detector_import_audit is not None else {}))
        result = joint_publication.run(options, raw_context=active_publication, early_regional=True,
                                       keep_selected_rows=True, geographic_projector=projection,
                                       reuse_cold_rows=True, reuse_grid_phase_states=True,
                                       phase_forecast=phase_forecast if forecast_audit is not None else None,
                                       no_active_curvature_sha256=no_active_curvature_sha256)
    if forecast_audit is not None:
        result["exact_phase_forecast"] = forecast_audit
    if survivor_witness is not None:
        result["named_survivor_finish"] = dict(requested=True, paid_final_fit=bool(survivor_witness))
    if grid_library is not None:
        result["grid_feature_projection"] = dict(grid_audit, source_sha256={
            name: sha256((HERE / name).read_bytes()).hexdigest()
            for name in ("grid_feature_projection.py", "grid_feature_projection.c")
        })
    return result["receipt"], result


def run(args, *, publisher=None):
    import empty_bootstrap as staged

    started = staged.now()
    if (getattr(args, "direct_residual_figures", False) or getattr(args, "direct_orbit_figures", False)) and not args.one_pass_web_png:
        raise ValueError("Direct figure rendering requires --one-pass-web-png")
    adaptive_map = getattr(args, "research_adaptive_position_map", False)
    if adaptive_map and not args.one_pass_web_png:
        raise ValueError("The research map requires --one-pass-web-png")
    lane_mask = getattr(args, "short_lane_mask", None)
    eight_ms = getattr(args, "eight_ms_native_history", False)
    full_primary_nonanchors = getattr(args, "full_primary_nonanchors", False)
    full_anchor_primary = getattr(args, "full_anchor_primary_library", None)
    strict_packed_eight = getattr(args, "strict_packed_eight", False)
    whole_blocks = getattr(args, "whole_stereo_blocks", False)
    if strict_packed_eight and (not eight_ms or full_anchor_primary is not None
                                or getattr(args, "packed_ci16_map", None) is None):
        raise ValueError("Strict packed input requires the complete 20/8 ms receiver and a trusted packed map")
    if full_anchor_primary is not None and not eight_ms:
        raise ValueError("Primary-only anchors require all-visit native 8 ms and its held selector")
    if eight_ms and (whole_blocks or lane_mask or getattr(args, "select_before_cfo", False) or not args.held_anchor_route):
        raise ValueError("Native 8 ms requires the complete unrefined schedule and held-anchor routing")
    if whole_blocks and (lane_mask or getattr(args, "held_anchor_route", False)
                         or getattr(args, "select_before_cfo", False) or getattr(args, "packed_ci16_map", None)):
        raise ValueError("Whole stereo scheduling requires the original unfiltered receiver and input reader")
    if lane_mask and getattr(args, "held_anchor_route", False):
        raise ValueError("The held-anchor selector requires measured outcomes on both donor lanes")
    if args.output.exists() or not args.output.parent.is_dir():
        raise ValueError("Choose a new local publication directory beneath an existing parent")
    launcher, specification, sources, publication, checks = staged.load_runtime()
    from combined_frontier_run import BLOCK_SHA, PREFETCH_FILES, load_prefetch
    from full_short_raw import observe_acquisition
    from full_short_run import (EIGHT_MS_RECIPES, EIGHT_MS_SHA, GEOGRAPHIC_SHA, RECIPE_SHA, SHORT_SHA,
                                SPARSE_EIGHT_MS_SHA, TRACK_SCORES_SHA, checked_recipe)
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.digests import canonical_digest
    from mixed_aperture_receiver import MixedApertureDetector
    from tools.pipeline_eval.variants.experimental.paired_sha256 import paired_decoded_hashes
    from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer

    sparse8 = getattr(args, "sparse8_primary", False)
    if sparse8 and (not eight_ms or full_anchor_primary is not None):
        raise ValueError("Sparse short primary requires native 8 ms and original two-scan anchors")
    short_pin = (SPARSE_EIGHT_MS_SHA if sparse8 else EIGHT_MS_SHA) if eight_ms else SHORT_SHA
    inputs = ((args.geographic_library, GEOGRAPHIC_SHA), (args.regional_track_library, TRACK_SCORES_SHA),
              (args.frontier_block_library, BLOCK_SHA))
    if full_primary_nonanchors:
        if (sparse8 or full_anchor_primary is not None or lane_mask or whole_blocks or strict_packed_eight
                or getattr(args, "select_before_cfo", False) or getattr(args, "packed_ci16_map", None) is not None):
            raise ValueError("Full-aperture primaries require the original every-visit stereo path")
    else:
        if args.short_binary is None:
            raise ValueError("Provide the authenticated short receiver binary")
        inputs = ((args.short_binary, short_pin), *inputs)
    for path, pin in inputs:
        staged.checked(path, pin)
    if args.one_pass_web_png:
        staged.checked(HERE / "one_pass_web_png.py", LAYOUT_SHA256)
    if full_primary_nonanchors:
        from full_primary_nonanchor_receiver import FullPrimaryNonanchor, recipe as full_primary_recipe

        original_recipe = full_primary_recipe()
        effective_detector = canonical_digest(original_recipe)[7:]
    else:
        original_recipe = checked_recipe(eight_ms=True, short_pin=short_pin) if eight_ms else checked_recipe()
        effective_detector = EIGHT_MS_RECIPES[short_pin] if eight_ms else RECIPE_SHA
    recipe = original_recipe
    anchor_helper = None
    if full_anchor_primary is not None:
        from primary_anchor_8ms import RECIPE_FIELD, AnchorPrimaryMixer, bound_library, definition

        anchor_helper = bound_library(full_anchor_primary)
        recipe = dict(original_recipe, **{RECIPE_FIELD: definition()})
        effective_detector = canonical_digest(recipe)[7:]
    if full_primary_nonanchors:
        mixer = FullPrimaryNonanchor(specification["detector"])
    elif lane_mask:
        from stereo_lane_receiver import StereoLaneReceiver
        from stereo_lane_schedule import recipe as mask_recipe

        recipe = mask_recipe(lane_mask, "sha256:" + RECIPE_SHA)
        effective_detector = canonical_digest(recipe).removeprefix("sha256:")
        mixer = StereoLaneReceiver(args.short_binary, SHORT_SHA, lane_mask)
    else:
        mixer = (MixedApertureDetector(args.short_binary, short_pin, full_coverage=True) if anchor_helper is None
                 else AnchorPrimaryMixer(args.short_binary, short_pin, anchor_helper))
    if whole_blocks:
        from live_stereo_blocks import bind

        recipe = bind(mixer, "sha256:" + RECIPE_SHA)
        effective_detector = canonical_digest(recipe)[7:]
    frequency_changes = None
    if getattr(args, "select_before_cfo", False):
        if lane_mask or getattr(args, "held_anchor_route", False) or "fixed_epoch_cfo_refinement" not in recipe:
            raise ValueError("Selection before CFO requires a refined full-coverage receiver and a single selector")
        from held_cycle_refined import FrequencyChanges

        frequency_changes = FrequencyChanges()
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
    packed_audit = None
    route_selection = None
    graph_audit = {} if args.exact_graph_reuse else None
    png_read_audit = {} if args.reuse_verified_png_reads else None
    detector_import_audit = {} if args.lazy_scanner_detector else None
    with TemporaryDirectory() as temporary:
        assets = Path(temporary)
        anchor = specification["detector_sha256"]
        if anchor != original_recipe["installed_sha256"]:
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
        packed = nullcontext()
        if any(getattr(args, key, None) is not None for key in
               ("packed_ci16_map", "packed_ci16_map_sha256", "packed_ci16_codec")):
            from packed_combined_input import packed_source, request

            packed_audit = {}
            packed = packed_source(scan, request(args), assets, packed_audit, strict_eight=strict_packed_eight)
        with (frequency_changes.capture(mixer.policy) if frequency_changes is not None else nullcontext(),
              receiver_import(native_import, symbols), packed, observe_acquisition(scan, mixer, effective_detector, audit),
              compressed_input_buffer(), paired_decoded_hashes(library), fetch() as prefetch):
            native = scan.acquire(session, inventory_digest, inventory, assets)
        staged.bind_native(native, session, inventory_digest, effective_detector)
        phases["authenticated_raw_acquisition"] = staged.clock(scope)
        if args.region.read_bytes() != offer_bytes:
            raise ValueError("The offered region changed during acquisition")
        if frequency_changes is not None:
            from held_cycle_refined import select_refined

            scope = staged.now()
            decision_file = args.output.with_name(args.output.name + "-held-cycle-refined.json")
            native, recipe, effective_detector, route_selection = select_refined(
                native, recipe, frequency_changes, session, inventory_digest, decision_file)
            phases["held_anchor_route_selection"] = staged.clock(scope)
        elif getattr(args, "held_anchor_route", False) and not full_primary_nonanchors:
            if eight_ms:
                from eight_ms_native_receiver import prepare
            else:
                from held_anchor_route_publication import prepare

            scope = staged.now()
            decision_file = args.output.with_name(args.output.name + "-held-anchor-route.json")
            native, recipe, effective_detector, route_selection = prepare(native, recipe, session, inventory_digest, decision_file)
            phases["held_anchor_route_selection"] = staged.clock(scope)
        scope = staged.now()
        reason = staged.empty_reason(native, frequency_evidence)
        graph_proof = None
        time_proof = getattr(args, "prove_graph_time_support", False)
        curvature_proof = getattr(args, "prove_no_active_curvature", False)
        if reason is None and (args.prove_empty_graph or time_proof or curvature_proof):
            from short_graph_guard import prove

            graph_proof = prove(native, assets, use_time_support=time_proof, use_curvature_extent=curvature_proof)
            if (args.prove_empty_graph or time_proof) and graph_proof["proven"]:
                reason = "no_active_curvature"
        before = [name for name in staged.SCIENTIFIC_IMPORTS if name in sys.modules]
        if before:
            raise ValueError(f"Scientific imports crossed the receiver-first boundary: {before}")
        handoff = Handoff(session, inventory_digest, effective_detector, native)
        if reason is None:
            extent = (graph_proof or {}).get("curvature_extent", {})
            with (adaptive_map_layout(args.output) if adaptive_map else nullcontext()):
                publish = publish_active if publisher is None else publisher
                terminal, research = publish(args, publication, specification, handoff, layout_audit,
                                                    graph_audit=graph_audit, png_read_audit=png_read_audit,
                                                    detector_import_audit=detector_import_audit,
                                                    no_active_curvature_sha256=extent.get("native_sha256"))
            route = research.get("raw_route", "optimized_installed_graph")
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
    if getattr(args, "named_survivor_finish", False):
        dependencies += ("isolated_salvage.py", "endpoint_track_repair.py", "fragment_gate_cross.py",
                         "provisional_salvage.py", "named_survivor_fit.py")
    if png_read_audit:
        dependencies += ("verified_png_reads.py",)
    if detector_import_audit:
        dependencies += ("lazy_scanner_detector.py",)
    if route_selection is not None:
        dependencies += ("held_anchor_route_publication.py", "anchor_cycle_route.py")
    if full_primary_nonanchors:
        dependencies += ("full_primary_nonanchor_receiver.py", "mixed_aperture_receiver.py")
    elif eight_ms:
        dependencies += ("eight_ms_native_receiver.py", "eight_ms_held_fit.py")
    if anchor_helper is not None:
        dependencies += ("mixed_aperture_receiver.py", "primary_anchor_8ms.py")
    if frequency_changes is not None:
        dependencies += ("held_cycle_refined.py",)
    if lane_mask:
        dependencies += ("stereo_lane_schedule.py", "stereo_lane_receiver.py")
    if whole_blocks:
        dependencies += ("live_stereo_blocks.py",)
    if packed_audit is not None:
        dependencies += ("packed_combined_input.py", "seekable_member.py", "ci16_packing.py", "ci16_packing.c")
    if strict_packed_eight:
        dependencies += ("seekable_eight_raw.py",)
    if adaptive_map:
        dependencies += ADAPTIVE_MAP_SOURCES
    result = dict(schema_version=1, implementation="unified signed raw research receiver and solver",
                  route=route, requested_offer_sha256=sha256(offer_bytes).hexdigest(), archive_root=str(archive),
                  frozen_specification="sha256:"+launcher["FINGERPRINT"], receiver_recipe=recipe,
                  detector_recipe_sha256="sha256:"+effective_detector, stock_launcher_sha256=staged.BASELINE_PIN,
                  native_sha256=native_sha, clock_anchor=native["clock_anchor"],
                  causal_cutoff_utc_ns=native["clock_anchor"]["before"]["realtime_ns"], receipt=terminal,
                  source_sha256={name: sha256((HERE / name).read_bytes()).hexdigest() for name in dependencies},
                  installed_acquisition_sources=staged.EXTRA_SOURCES,
                  solver_source_sha256=None if research is None else research["source_sha256"],
                  graph_proof=graph_proof,
                  named_survivor_finish=None if research is None else research.get("named_survivor_finish"),
                  exact_graph_reuse=dict(requested=args.exact_graph_reuse, executed=graph_audit or None),
                  verified_png_reads=png_read_audit,
                  scanner_detector_import=detector_import_audit,
                  one_pass_web_png=dict(enabled=args.one_pass_web_png,
                                        source_sha256=LAYOUT_SHA256 if args.one_pass_web_png else None, **layout_audit),
                  solver_recipe=dict(graph="installed", block_sha256=BLOCK_SHA, scalar_track_sha256=TRACK_SCORES_SHA,
                                     geographic_sha256=GEOGRAPHIC_SHA, reuse_cold_rows=True,
                                     reuse_grid_phase_states=True, skip_empty_proof=True),
                  prefetch_sources=PREFETCH_FILES, prefetch=asdict(prefetch), raw_acquisitions=1,
                  verified_handoffs=handoff.calls, receiver_audit=audit, phases=phases,
                  scientific_imports_before=before, scientific_imports_after=after,
                  total_before_receipt=staged.clock(started))
    if publisher is not None:
        result["solver_recipe"] = None if research is None else research["solver_recipe"]
    if research is not None and "grid_feature_projection" in research:
        result["grid_feature_projection"] = research["grid_feature_projection"]
    if getattr(args, "exact_phase_forecast", False):
        result["exact_phase_forecast"] = (dict(requested=True, executions=[]) if research is None
                                          else research["exact_phase_forecast"])
    if route_selection is not None:
        result["held_anchor_route"] = route_selection
    if packed_audit is not None:
        result["packed_ci16_input"] = packed_audit
    if adaptive_map:
        result["research_adaptive_position_map"] = dict(
            namespace="research-adaptive-position-v1", published=research is not None and terminal["decision"] == "complete")
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
    parser.add_argument("--prove-graph-time-support", action="store_true",
                        help="Prove no graph path spans the required time on small signed packets")
    parser.add_argument("--prove-no-active-curvature", action="store_true",
                        help="Keep named-v3 withholding precedence when every authenticated lane is shorter than 20 seconds")
    parser.add_argument("--named-survivor-finish", action="store_true",
                        help="Isolate a disputed satellite family and run the original qualified final fit on the accepted observations")
    parser.add_argument("--select-before-cfo", action="store_true",
                        help="Select lanes by held-anchor prediction before applying their refined carrier frequencies")
    parser.add_argument("--withhold-empty-family-calibration", action="store_true",
                        help="Withhold when the nominated family's exclusion leaves zero independent calibration observations")
    parser.add_argument("--prove-empty-graph", action="store_true",
                        help="Use the pinned minimum support proof before loading the numerical solver")
    parser.add_argument("--one-pass-web-png", action="store_true",
                        help="Use the reviewed explicit layout on the installed renderer when supported")
    parser.add_argument("--research-adaptive-position-map", action="store_true",
                        help="Publish measured adaptive map points and figures in the separate research namespace")
    parser.add_argument("--direct-residual-figures", action="store_true",
                        help="Draw the two residual plots directly with Cairo when the explicit layout is enabled")
    parser.add_argument("--direct-orbit-figures", action="store_true",
                        help="Draw the four shared orbit plots directly with Cairo when the explicit layout is enabled")
    parser.add_argument("--exact-graph-reuse", action="store_true",
                        help="Use reviewed ordered graph batches and exact best-piece reuse in active lanes")
    parser.add_argument("--reuse-verified-png-reads", action="store_true",
                        help="Decode each new PNG from its original verified publication read")
    parser.add_argument("--grid-feature-projection-library", type=Path,
                        help="Use the verified experimental grid projection and selected row library")
    parser.add_argument("--lazy-scanner-detector", action="store_true",
                        help="Load the installed detector adapter on first detector use in active publication")
    parser.add_argument("--exact-phase-forecast", action="store_true",
                        help="Reuse exact validation UTC splits in the reviewed active phase forecast")
    parser.add_argument("--held-anchor-route", action="store_true",
                        help="Choose unfiltered or full chronological carrier history by held full-anchor log scores")
    parser.add_argument("--eight-ms-native-history", action="store_true",
                        help="Use the pinned 8 ms primary with --held-anchor-route and no CFO tail")
    parser.add_argument("--full-anchor-primary-library", type=Path,
                        help="Use the pinned original rank-zero scan for every 20 ms anchor in all-visit native 8 ms")
    parser.add_argument("--short-lane-mask", choices=("quarter", "target"),
                        help="Skip a scheduled short antenna call while keeping both full anchors")
    parser.add_argument("--whole-stereo-blocks", action="store_true",
                        help="Keep each full anchor and two of every three unfiltered short stereo visits")
    parser.add_argument("--packed-ci16-map", type=Path, help="Private packed member map with sibling member directories")
    parser.add_argument("--packed-ci16-map-sha256", help="Trusted digest of the packed member map")
    parser.add_argument("--packed-ci16-codec", type=Path, help="Native codec library pinned by the map")
    parser.add_argument("--strict-packed-eight", action="store_true",
                        help="Authenticate every encoded block and decode the exact 8 ms/full native aperture")
    print(json.dumps(run(parser.parse_args()), allow_nan=False))
