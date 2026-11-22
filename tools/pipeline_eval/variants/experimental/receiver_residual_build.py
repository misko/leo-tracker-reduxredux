"""Compile an opt-in raw-factor entry from the pinned packed two-scan source."""

import argparse
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from . import receiver_build

PACKED_SHA256 = "950c2b9412020317654fd7c79d30063e9258b70152ed9c91b4129d379ac75a13"
FRACTIONAL_BATCH_SHA256 = "c5fca3e240f5415a061ce17057ef215070767d23cae4932b9a1d566217eae420"
TWO_CARRIER_SOURCE = receiver_build.PINNED / "tools/pipeline_eval/variants/two_carrier_receiver.c"


def optional_residual(source):
    edits = (
        ("TwoCarrierPeak out[2], ScanFactor *factors) {",
         "TwoCarrierPeak out[2], ScanFactor *factors, int scan_residual) {"),
        ("    if (pilot_cancel(iq, r->residual, lane, r->synthesis, "
         "r->rotated, p[0].epoch, p[0].hz) ||\n"
         "        timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]) ||\n"
         "        portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;",
         "    if (scan_residual &&\n"
         "        (pilot_cancel(iq, r->residual, lane, r->synthesis, "
         "r->rotated, p[0].epoch, p[0].hz) ||\n"
         "         timing_first_detect(r->timing, r->residual, lane, lo, hi, &p[1]))) return -1;\n"
         "    if (portable_verifier_load(r->verify, iq, (unsigned)lane)) return -1;"),
        ("for (int i = 0; i < 2; ++i) {", "for (int i = 0; i < 1 + scan_residual; ++i) {"),
        ("measure(r, iq, lane, lo, hi, out, NULL)", "measure(r, iq, lane, lo, hi, out, NULL, 1)"),
        ("measure(r, iq, lane, lo, hi, peaks, out)", "measure(r, iq, lane, lo, hi, peaks, out, 1)"),
    )
    for before, after in edits:
        source = receiver_build.replace(source, before, after)
    return source + """
int cancellation_primary_factors(TwoCarrierReceiver *r, const int16_t *iq, int lane,
                                 double lo, double hi, ScanFactor out[2]) {
    TwoCarrierPeak peaks[2];
    return out ? measure(r, iq, lane, lo, hi, peaks, out, 0) : -1;
}
"""


def build(output, *, fractional_batch=False, profile=False, integer_fir=False):
    """Reproduce the chosen frozen kernel before adding the optional entry."""
    output = Path(output).resolve()
    read_text = Path.read_text
    recipe = dict(pack_stencil=True, batch_refine=fractional_batch,
                  fractional_batch=fractional_batch)
    expected = FRACTIONAL_BATCH_SHA256 if fractional_batch else PACKED_SHA256

    def source(path, *args, **kwargs):
        text = read_text(path, *args, **kwargs)
        return optional_residual(text) if path == TWO_CARRIER_SOURCE else text

    with TemporaryDirectory(dir=output.parent) as directory:
        frozen = Path(directory) / "frozen.so"
        receiver_build.build(frozen, **recipe)
        if sha256(frozen.read_bytes()).hexdigest() != expected:
            raise ValueError("Packed build recipe did not reproduce the frozen receiver")
        # The build validates source bytes via read_bytes before reading its text.
        with patch.object(Path, "read_text", source):
            receiver_build.build(output, profile=profile, integer_fir=integer_fir, **recipe)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fractional-batch", action="store_true")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--integer-fir", action="store_true")
    args = parser.parse_args()
    build(args.output, fractional_batch=args.fractional_batch, profile=args.profile,
          integer_fir=args.integer_fir)
