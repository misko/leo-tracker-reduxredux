"""Relink a pinned native primary over eight unchanged hardware frame origins."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

from . import mixed_aperture_trial, short_signed_trial
from .directed_verifier_trial import replace_once
from .eight_ms_primary import HERE, write
from .scout_readout_trial import check_machine


FRAMES = (0, 1, 4, 5, 8, 9, 12, 13)
SAMPLES = 200_000
STRIDE = 4
WIDTH = round(10_000_000 / (750 * STRIDE)) + 128 * 44 // STRIDE - 1
FIR_PAD = 40
INCLUDES = {
    "receiver_refine_batch.inc": ("700626f50e8c66d52e4076e0ab3821a691de566f849796ab365a913d3cf3cce8",
                                  "(40000*f + 1)/3", "(40000*native_frame[f] + 1)/3"),
    "receiver_simd.inc": ("3672b6f8b1aa8683783371553fcae2de2e2069dcf1642622e2fefbaff9e076a8",
                          "(40000 * f + 1) / 3", "(40000 * native_frame[f] + 1) / 3"),
}


def origin(frame, stride=1):
    return round(frame * 10_000_000 / (750 * stride))


def ranges_for_fir():
    """Enclose the selected dependencies on the exact original four-output tile grid."""
    ranges = []
    pad = FIR_PAD // STRIDE
    for early, late in zip(FRAMES[::2], FRAMES[1::2], strict=True):
        first = origin(early, STRIDE) + 88 // STRIDE
        end = origin(late, STRIDE) + 88 // STRIDE + WIDTH
        start_tile = pad + (first - pad) // 4 * 4
        last_tile = pad + (end - pad + 3) // 4 * 4
        if not pad <= start_tile < last_tile <= SAMPLES // STRIDE - pad:
            raise ValueError("Selected frame crosses a full-window FIR clipping boundary")
        ranges.append((start_tile, last_tile))
    if any(a[1] >= b[0] for a, b in zip(ranges, ranges[1:])):
        raise ValueError("Expected four independent FIR-output groups")
    return tuple(ranges)


def possible_input_dependencies():
    """Keep every native read that could affect any selected proposal or confirmation."""
    # FIR ranges include their original SIMD block rounding and full input halos.
    # The late f+232 symbol check with the latest wrapped epoch is the largest
    # full-rate right dependency. The protected halo also covers the stencil.
    last = 13_332 + 88 + (232 + 64) * 44
    return tuple((min(origin(first)-16, start*STRIDE-FIR_PAD),
                  max(origin(second)+last+16, (end-1)*STRIDE+FIR_PAD+1))
                 for (first, second), (start, end) in zip(zip(FRAMES[::2], FRAMES[1::2], strict=True),
                                                          ranges_for_fir(), strict=True))


def make_transform(includes, *, sparse_fir):
    frozen_short_source = short_signed_trial.short_source
    frame_map = "static const int native_frame[8] = {" + ", ".join(map(str, FRAMES)) + "};\n"

    def edits(name, before, samples, frames):
        if (samples, frames) != (SAMPLES, len(FRAMES)):
            raise ValueError("Unexpected distributed frame geometry")
        text = frozen_short_source(name, before, samples, frames)
        if name == "timing_first_receiver":
            return frame_map + replace_once(text, "frame * 1e7 /", "native_frame[frame] * 1e7 /")
        if name == "delay_product_kernel":
            old = "(40000*f+1)/3"
            if text.count(old) != 2:
                raise ValueError("Unexpected scalar and packed delay refinement schedules")
            text = text.replace(old, "(40000*native_frame[f]+1)/3")
            for header, (pin, old, new) in INCLUDES.items():
                source = short_signed_trial.verified(includes / header, pin).decode()
                text = replace_once(text, f'#include "{header}"', replace_once(source, old, new))
            return frame_map + text
        if name == "portable_verifier":
            return frame_map + replace_once(text, "(frame*40000 + 1)/3", "(native_frame[frame]*40000 + 1)/3")
        if name == "tile" and sparse_fir:
            intervals = ", ".join(f"{{{a}, {b}}}" for a, b in ranges_for_fir())
            begin = (f"    const int interval[4][2] = {{{intervals}}};\n"
                     "    for (int run = 0; run < 4; ++run) {\n"
                     "    for (int j = interval[run][0]; j < interval[run][1]; j += 4) {")
            text = replace_once(text, "    for (int j = pad; j < output_samples - pad; j += 4) {", begin)
            return replace_once(text, "    for (int j = output_samples - pad;", "    }\n    for (int j = output_samples - pad;")
        return text

    return edits


def build(archive, root, installed, assets):
    machine = check_machine()
    root.mkdir()
    include_dir = Path("/tmp/leo-algo08v2-2x/tools/pipeline_eval/variants/experimental")
    results = {}
    for arm in ("full-fir", "selected-fir"):
        stage, primary = root / (arm + "-scout"), root / arm
        transform = make_transform(include_dir, sparse_fir=arm == "selected-fir")
        with patch.object(short_signed_trial, "short_source", transform):
            result = short_signed_trial.build(archive, stage, installed, assets,
                                              apertures={arm: (SAMPLES, len(FRAMES))})
        mixed_aperture_trial.build(archive, primary, short=result["arms"][arm])
        results[arm] = dict(scout=result, primary=json.loads((primary / "build-receipt.json").read_bytes()))
    write(root / "build.json", dict(
        frames=FRAMES, sample_rate_hz=10_000_000, samples=SAMPLES, scout_frame_width_at_stride4=WIDTH,
        selected_fir_ranges=ranges_for_fir(), possible_input_dependencies=possible_input_dependencies(),
        machine=machine, results=results,
        source_pins={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
            "distributed_aperture.py", "distributed-aperture-protocol.md", "short_signed_trial.py", "mixed_aperture_trial.py",
        )},
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("archive", "root", "installed", "assets"):
        parser.add_argument(name, type=Path)
    build(**vars(parser.parse_args()))
