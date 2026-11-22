"""Compute a certified upper bound on the integer refinement score by parity."""

from .receiver_build import HERE, replace


def kernel_overlay(source):
    batch = (HERE / "receiver_refine_batch.inc").read_text()
    batch = replace(batch, "int epoch, BlockMatrix *matrix)",
                    "int epoch, BlockMatrix *matrix, int first_frame, int frame_stride)")
    batch = replace(batch, "for (int f = 0; f < frames; ++f)",
                    "for (int f = first_frame; f < frames; f += frame_stride)")
    for arity in (1, 2):
        batch = replace(batch, f"rotation, {arity}, seed.epoch, matrix);",
                        f"rotation, {arity}, seed.epoch, matrix, 0, 1);")
    parity = (HERE / "receiver_refine_parity.inc").read_text()
    return replace(source, '#include "receiver_refine_batch.inc"', batch + "\n" + parity)


def timing_overlay(source):
    source = '#include "receiver_refine_parity.h"\n' + source
    source = replace(source, "    Peak peaks[max_peaks];\n", "")
    source = replace(source, "static void input(", '#include "receiver_refine_parity_timing.inc"\n\n'
                     "static void input(")
    start = source.index("    double v[max_peaks][4];")
    end = source.index("\n}", start)
    return source[:start] + "    return refine_confirmed(w, request, done, lo, hi, out);" + source[end:]
