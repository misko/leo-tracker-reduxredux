"""Run the research full-short receiver and solver with a caller-supplied region."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from aperture_trial import write
from full_short_raw import GRAPH, RECIPE_SHA, SHORT_SHA, graph_config, observe_acquisition, recipe
from joint_publication import run
from mixed_aperture_receiver import MixedApertureDetector


GEOGRAPHIC_SHA = "b8c8e0bb22e62fc69585909f193c76ab22ab4f2892d7fcbedd2cc31c78c573ee"


@contextmanager
def geographic_projection(binary):
    from dense_geographic_projection import Projector, checked_runtime

    kernel, original = checked_runtime()
    native = Projector(binary, GEOGRAPHIC_SHA, original)
    with patch.object(kernel, "phase_linear_frequency", native):
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
    parser.add_argument("--saved-digest", help="Canonical detector packet digest from its original terminal")
    parser.add_argument("--geographic-library", type=Path, help="Use the reviewed native projection in regional checks")
    parser.add_argument("--reuse-cold-track-rows", action="store_true",
                        help="Reuse nominal centre rows in full-catalogue cold rank")
    parser.add_argument("--track-graph", choices=("quadratic", "installed"), default="quadratic",
                        help="Track configuration to use after the signed receiver handoff")
    parser.add_argument("--profiled-gamma-library", type=Path,
                        help="Use the reviewed profiled Gamma fit on saved detections")
    args = parser.parse_args(argv)
    if bool(args.saved) != bool(args.saved_digest):
        parser.error("--saved and --saved-digest must be used together")
    if args.profiled_gamma_library is not None and not args.saved:
        parser.error("--profiled-gamma-library requires --saved")
    args.optimized_full_catalogue = True
    args.verify_images = True
    identity = checked_recipe()
    audit = {}
    quadratic = args.track_graph == "quadratic"
    receiver = MixedApertureDetector(args.short_binary, SHORT_SHA, full_coverage=True) if args.short_binary else None
    run(args, detector_override=receiver.detector if receiver else None,
        detector_description="verified raw stereo with full anchors and 12 ms primaries",
        track_config=graph_config if quadratic else None, early_regional=True, keep_selected_rows=True,
        raw_context=(lambda scan: observe_acquisition(scan, receiver, RECIPE_SHA, audit)) if receiver else None,
        saved_receiver=None if receiver else RECIPE_SHA,
        geographic_projector=(lambda: geographic_projection(args.geographic_library)) if args.geographic_library else None,
        reuse_cold_rows=args.reuse_cold_track_rows,
        **({"profiled_gamma_library": args.profiled_gamma_library} if args.profiled_gamma_library is not None else {}))
    write(args.output / "full-short-recipe.json", dict(recipe=identity, graph=GRAPH if quadratic else "installed",
             receiver_audit=audit,
             saved_digest=args.saved_digest, geographic_sha256=GEOGRAPHIC_SHA if args.geographic_library else None,
             **({"reuse_cold_track_rows": True} if args.reuse_cold_track_rows else {}),
             **({"profiled_gamma": True} if args.profiled_gamma_library is not None else {})))


if __name__ == "__main__":
    main()
