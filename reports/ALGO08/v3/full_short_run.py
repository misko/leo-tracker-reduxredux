"""Run the research full-short receiver and solver with a caller-supplied region."""

import argparse
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import write
from full_short_raw import GRAPH, RECIPE_SHA, SHORT_SHA, graph_config, observe_acquisition, recipe
from joint_publication import run
from mixed_aperture_receiver import MixedApertureDetector


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
    args = parser.parse_args(argv)
    if bool(args.saved) != bool(args.saved_digest):
        parser.error("--saved and --saved-digest must be used together")
    args.optimized_full_catalogue = True
    args.verify_images = True
    identity = checked_recipe()
    audit = {}
    receiver = MixedApertureDetector(args.short_binary, SHORT_SHA, full_coverage=True) if args.short_binary else None
    run(args, detector_override=receiver.detector if receiver else None,
        detector_description="verified raw stereo with full anchors and 12 ms primaries",
        track_config=graph_config, early_regional=True, keep_selected_rows=True,
        raw_context=(lambda scan: observe_acquisition(scan, receiver, RECIPE_SHA, audit)) if receiver else None,
        saved_receiver=None if receiver else RECIPE_SHA)
    write(args.output / "full-short-recipe.json", dict(recipe=identity, graph=GRAPH, receiver_audit=audit,
                                                        saved_digest=args.saved_digest))


if __name__ == "__main__":
    main()
