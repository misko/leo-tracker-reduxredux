"""Compose the checked sparse receiver and positive-only rank and PNG ports."""

from contextlib import contextmanager
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import combined_successor_cairo_entry as cairo
import combined_successor_raw_entry as guarded


PNG_LIBRARY = Path("/dev/shm/leo-v3-positive-overhead-results-02/unfilter.so")
PNG_SHA = "fe439ce97af62706b396bc7af50924867d2512ad61aca41c744268165a3c9be4"
SPARSE_LIBRARY = Path("/tmp/leo-v3-short-rank-transfer-DS30-0016-01/sparse/use.so")
HELD_SHA = "ce13caaadf150f474a024fda7da31a33f9e293e9bb9e4d91613c552c3cd7335a"


def verification_factory(cls, audit):
    def make(root, original_decode, png_audit):
        from PIL import Image
        from verified_rgba import LIMIT, RgbaEvidence

        if Image.MAX_IMAGE_PIXELS is None or Image.MAX_IMAGE_PIXELS >= LIMIT//4:
            decode = RgbaEvidence(PNG_LIBRARY, PNG_SHA, original_decode, audit)
        else:
            audit["unavailable"] = "stricter Pillow pixel limit"
            decode = original_decode
        return cls(root, decode, png_audit)

    return make


@contextmanager
def positive_ports(original, spec, audit):
    import exact_named_raw as raw

    publish = raw.publish_active

    def accelerated(*args, **kwargs):
        from tools import algo08_position, algo08_scan  # Bind the installed runtime first.
        import verified_png_reads as png
        from single_rank_refusal import single_rank_refusal

        if not callable(algo08_position.solve) or not callable(algo08_scan.solve):
            raise ValueError("The installed positive solver is unavailable")
        with (single_rank_refusal(),
              patch.object(png, "VerifiedPngReads", verification_factory(png.VerifiedPngReads, audit.setdefault("png_native", {})))):
            return publish(*args, **kwargs)

    with patch.object(raw, "publish_active", accelerated), original(spec, audit):
        yield


def main():
    import legacy_first_map_entry as receiver

    parser = receiver.parser
    original = guarded.solver_ports
    original_smoke = guarded.smoke

    def options():
        cli = parser()
        cli.add_argument("--sparse8-primary", action="store_true", required=True)
        cli.add_argument("--guarded-full-anchor-library", type=Path,
                         help="Research-only guarded full anchors with the original sparse 8 ms primary")
        return cli

    def smoke(args, acceleration):
        from verified_rgba import RgbaEvidence

        if not RgbaEvidence(PNG_LIBRARY, PNG_SHA, None, {}).ready:
            raise ValueError("The independent native PNG verification ABI is unavailable")
        original_smoke(args, acceleration)

    with (patch.object(receiver, "parser", options),
          patch.object(guarded, "solver_ports", lambda spec, audit: positive_ports(original, spec, audit)),
          patch.object(guarded, "smoke", smoke)):
        cairo.main()


if __name__ == "__main__":
    main()
