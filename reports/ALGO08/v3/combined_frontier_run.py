"""Run signed full-short acquisition with bounded prefetch and exact regional probe blocks."""

import argparse
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from importlib import import_module
from pathlib import Path
import sys
from unittest.mock import patch

from aperture_trial import write
import full_short_run
import joint_publication


HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2] / "tools/pipeline_eval/variants/experimental"
PREFETCH_SHA = "05b3b619429e1e35c9e9f811b3a68e68df6a6f6b37e7c05338dccd91fb0db8cc"
BLOCK_SHA = "adfbfca33caee3c6b337ddf401db1112e525867e451ad010eb30cb65965ce042"
PREFETCH_FILES = {
    "receiver_ingress": "c58f76ae56022aca3893b04bfe4732f24185e9b98294c543a31abf752c264fa8",
    "receiver_member_lookahead": "3e89683eeea48443d6a6c9cf81c843189ccfa4638206e7f57e182489c905791e",
    "receiver_member_prefetch": PREFETCH_SHA,
}


def verify(path, expected):
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Unrecognized implementation: {path}")


def load_prefetch():
    with patch.object(sys, "path", [str(BASE.parent), *sys.path]):
        for name, expected in PREFETCH_FILES.items():
            source = BASE / f"{name}.py"
            verify(source, expected)
            module = import_module("experimental." + name)
            if Path(module.__file__).resolve() != source:
                raise ValueError(f"Unexpected source for {name}")
        return import_module("experimental.receiver_member_prefetch").compressed_member_prefetch


def main():
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--frontier-block-library", required=True, type=Path)
    parser.add_argument("--short-binary", required=True, type=Path)
    parser.add_argument("--regional-track-library", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    options, rest = parser.parse_known_args()
    verify(options.frontier_block_library, BLOCK_SHA)
    verify(options.regional_track_library, full_short_run.TRACK_SCORES_SHA)
    publication, spec = joint_publication.configuration()
    from regional_probe_block_binding import guarded_projection

    fetch = load_prefetch()
    if spec.get("ingress") != "paired-sha256" or not spec.get("member_lookahead"):
        raise ValueError("Expected the verified receiver ingress with lookahead enabled")
    original_hint = publication._checked_member_lookahead
    original_projection = full_short_run.geographic_projection
    acquisitions = []

    @contextmanager
    def tracked():
        with fetch() as stats:
            yield stats
        acquisitions.append(asdict(stats))

    def read_ahead(candidate_spec):
        original_hint(candidate_spec)
        return tracked

    def project(single, tracks):
        return guarded_projection(single, tracks, options.frontier_block_library, original_projection)

    with (patch.object(joint_publication, "configuration", return_value=(publication, spec)),
          patch.object(publication, "_checked_member_lookahead", read_ahead),
          patch.object(full_short_run, "geographic_projection", project)):
        full_short_run.main([*rest, "--short-binary", str(options.short_binary), "--regional-track-library",
                             str(options.regional_track_library), "--output", str(options.output)])
    if len(acquisitions) != 1:
        raise ValueError("Expected one verified raw acquisition")
    write(options.output / "combined-frontier.json", dict(prefetch=acquisitions[0],
          block_sha256=BLOCK_SHA, prefetch_sources=PREFETCH_FILES, track_sha256=full_short_run.TRACK_SCORES_SHA,
          skip_empty_proof="--skip-empty-proof" in rest))


if __name__ == "__main__":
    main()
