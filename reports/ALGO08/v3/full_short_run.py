"""Run the research full-short receiver and solver with a caller-supplied region."""

import argparse
from contextlib import contextmanager, ExitStack
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import write
from full_short_raw import GRAPH, RECIPE_SHA, SHORT_SHA, graph_config, observe_acquisition, recipe
from joint_publication import run
from mixed_aperture_receiver import MixedApertureDetector


GEOGRAPHIC_SHA = "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee"
TRACK_SCORES_SHA = "5e96851c0f9c479dbb176eeb3f2ba143c461d590a9b35b00fb5c1d7ce984d098"


@contextmanager
def geographic_projection(binary, track_library=None):
    from dense_geographic_projection import Projector, checked_runtime

    kernel, original = checked_runtime()
    native = Projector(binary, GEOGRAPHIC_SHA, original)
    with ExitStack() as scope:
        scope.enter_context(patch.object(kernel, "phase_linear_frequency", native))
        if track_library is not None:
            from regional_track_scores import TrackScores

            if sha256(track_library.read_bytes()).hexdigest() != TRACK_SCORES_SHA:
                raise ValueError("Unpinned regional track likelihood library")
            prepare = kernel._prepare_probe_scores

            def prepare_tracks(*args):
                points, original_score, meta = prepare(*args)
                scorer = TrackScores(track_library, original_score)

                def score(point):
                    native_before = scorer.native
                    result = scorer(point)
                    native.counts["track_score_native"] += int(scorer.native > native_before)
                    native.counts["track_score_fallbacks"] += int(scorer.native == native_before)
                    return result

                return points, score, meta

            scope.enter_context(patch.object(kernel, "_prepare_probe_scores", prepare_tracks))
        yield native.counts


def checked_recipe():
    value = recipe()
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if sha256(encoded.encode()).hexdigest() != RECIPE_SHA:
        raise ValueError("The receiver callback or schedule changed")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("recording", "archive", "region", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--short-binary", type=Path, help="Pinned 12 ms primary library for raw acquisition")
    mode.add_argument("--saved", type=Path, help="Frozen full-short detections from the same recording")
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--causal-selection", action="store_true", help="Apply the existing causal carrier-history filter")
    selection.add_argument("--local-future-repair", action="store_true", help="Attach future-supported factors to fixed forward-owned tracks")
    parser.add_argument("--skip-empty-proof", action="store_true", help="Bypass catalogue propagation when there are no graph tracks to score")
    parser.add_argument("--saved-digest", help="Canonical detector packet digest from its original terminal")
    parser.add_argument("--geographic-library", type=Path, help="Use the reviewed native projection in regional checks")
    parser.add_argument("--regional-track-library", type=Path, help="Use the native track likelihood on fused regional projections")
    parser.add_argument("--reuse-cold-track-rows", action="store_true",
                        help="Reuse nominal centre rows in full-catalogue cold rank")
    parser.add_argument("--reuse-grid-phase-states", action="store_true",
                        help="Reuse interpolated satellite states on the full diagnostic grid")
    parser.add_argument("--track-graph", choices=("quadratic", "installed"),
                        help="Track configuration to use after the signed receiver handoff")
    parser.add_argument("--profiled-gamma-library", type=Path,
                        help="Use the reviewed profiled Gamma fit on saved detections")
    args = parser.parse_args(argv)
    if bool(args.saved) != bool(args.saved_digest):
        parser.error("--saved and --saved-digest must be used together")
    if args.profiled_gamma_library is not None and not args.saved:
        parser.error("--profiled-gamma-library requires --saved")
    if args.regional_track_library is not None and not args.geographic_library:
        parser.error("--regional-track-library requires --geographic-library")
    if args.local_future_repair and (args.track_graph == "quadratic" or args.profiled_gamma_library is not None):
        parser.error("--local-future-repair requires the installed graph and original Gamma fit")
    if args.track_graph is None:
        args.track_graph = "installed" if args.local_future_repair else "quadratic"
    args.optimized_full_catalogue = True
    args.verify_images = True
    identity = checked_recipe()
    detector_pin = RECIPE_SHA
    receiver_type = MixedApertureDetector
    if args.causal_selection:
        from causal_short_receiver import CausalShortReceiver, identity as causal_identity

        identity, detector_pin = causal_identity(RECIPE_SHA)
        receiver_type = CausalShortReceiver
    audit = {}
    policy = None
    if args.local_future_repair:
        from local_future_policy import LocalFuturePolicy

        policy = LocalFuturePolicy("raw" if args.short_binary else "saved")
    quadratic = args.track_graph == "quadratic"
    receiver = receiver_type(args.short_binary, SHORT_SHA, full_coverage=True) if args.short_binary else None
    result = run(args, detector_override=receiver.detector if receiver else None,
        detector_description="verified raw stereo with full anchors and 12 ms primaries",
        track_config=graph_config if quadratic else None, early_regional=True, keep_selected_rows=True,
        raw_context=(lambda scan: observe_acquisition(scan, receiver, detector_pin, audit)) if receiver else None,
        saved_receiver=None if receiver else detector_pin,
        geographic_projector=(lambda: geographic_projection(args.geographic_library, args.regional_track_library))
        if args.geographic_library else None,
        reuse_cold_rows=args.reuse_cold_track_rows, reuse_grid_phase_states=args.reuse_grid_phase_states,
        **({"local_future_policy": policy} if policy is not None else {}),
        **({"profiled_gamma_library": args.profiled_gamma_library} if args.profiled_gamma_library is not None else {}))
    policy_pin = {"solver_policy_sha256": policy.seal(args.output, result)} if policy is not None else {}
    write(args.output / "full-short-recipe.json", dict(recipe=identity, graph=GRAPH if quadratic else "installed",
             receiver_audit=audit,
             **policy_pin,
             **({"skip_empty_proof": True} if args.skip_empty_proof else {}),
             saved_digest=args.saved_digest, geographic_sha256=GEOGRAPHIC_SHA if args.geographic_library else None,
             **({"reuse_cold_track_rows": True} if args.reuse_cold_track_rows else {}),
             **({"reuse_grid_phase_states": True} if args.reuse_grid_phase_states else {}),
             **({"regional_track_sha256": TRACK_SCORES_SHA} if args.regional_track_library is not None else {}),
             **({"profiled_gamma": True} if args.profiled_gamma_library is not None else {})))


if __name__ == "__main__":
    main()
