"""Build an opt-in timing-first receiver from the digest-checked ALGO08v2 recipe."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
PINNED = HERE.parents[3] / "native/algo08v2"


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f"ALGO08v2 overlay source did not match {old!r}")
    return text.replace(old, new)


def fftw_timing(text, crop):
    edits = [
        ('#include "timing_first_receiver.h"', '#include "timing_first_receiver.h"\n#include <fftw3.h>'),
        ('    float fir[81];\n};', '    float fir[81];\n    fftwf_plan plans[3];\n};\n'
         '#include "receiver_fftw.inc"'),
        ('static void transform(TimingFirst *w, int n, int backward) {',
         'static void transform(TimingFirst *w, int n, int backward) {\n'
         '    if (transform_large(w, n, backward)) return;'),
        ('    free(w->scratch);', '    release_fft(w);'),
        ('    w->scratch = reserve(w, w->fft_size, sizeof(Sample));',
         '    w->allocated += w->fft_size * sizeof(Sample);\n'
         '    w->scratch = (Sample *)fftwf_alloc_complex(w->fft_size);'),
        ('    prepare(w);', '    if (!prepare_fft(w)) {\n'
         '        timing_first_free(w);\n        return NULL;\n    }\n    prepare(w);'),
    ]
    for old, new in edits:
        text = replace(text, old, new)
    if not crop:
        return text
    text = replace(text, '    fftwf_plan plans[3];', '    int correlation_size;\n    fftwf_plan plans[3];')
    text = replace(text, '#include "receiver_fftw.inc"',
                   '#define CORRELATION_SIZE(w) ((w)->correlation_size)\n#include "receiver_fftw.inc"')
    text = replace(text, '    w->fft_size = 32768 / stride;', '    w->fft_size = 32768 / stride;\n'
                   '    w->correlation_size = 19200 / stride;')
    text = replace(text, 'reserve(w, lags * w->fft_size, sizeof(Sample))',
                   'reserve(w, lags * w->correlation_size, sizeof(Sample))')
    # Each retained start fits the complete template in the received block.
    # The circular correlation only needs space for that received block.
    for begin, end in [('    for (int j = 0; j < lags; ++j)', 'void timing_first_free('),
                       ('static void find_times(', 'static double bin_hz(')]:
        left = text.index(begin)
        right = text.index(end, left)
        text = text[:left] + text[left:right].replace('w->fft_size', 'w->correlation_size') + text[right:]
    return text


def group_gate(text):
    begin = text.index('    for (int f = 0; f < count; ++f) {\n', text.index('static int gate('))
    end = text.index('    return 1;', begin)
    groups = text[begin:end]
    split = groups.index('    for (int i = 0; i < groups_used; ++i)\n')
    accumulate, compare = groups[:split], groups[split:].splitlines(keepends=True)[1:]
    accumulate = replace(accumulate, 'int f = 0; f < count; ++f',
                         'int f = i; f < count; f += groups_used')
    accumulate = replace(accumulate, 'groups[f % groups_used][b]', 'group[b]')
    compare = [replace(line, 'groups[i][b] >= groups[i][0]', 'group[b] >= group[0]')
               if 'groups[i]' in line else line for line in compare]
    text = replace(text, '    double groups[7][64] = {{0}};\n', '')
    return replace(text, groups, '    for (int i = 0; i < groups_used; ++i) {\n'
                   '        double group[64] = {0};\n'
                   + ''.join('    ' + line for line in accumulate.splitlines(keepends=True))
                   + ''.join(compare) + '    }\n')


def paired_fir(text):
    text = replace(text, 'static const double tau', '#include "receiver_simd.inc"\n\nstatic const double tau')
    return replace(text, '    int half = taps / 2;',
                   '    if (paired_fir(x, coeff, taps, stride, out)) return 0;\n    int half = taps / 2;')


def paired_refine(text):
    start = text.index('int delay_refine(')
    original = text[start:]
    packed = replace(original, 'int delay_refine(',
                     '__attribute__((target("avx2")))\nstatic int delay_refine_packed(')
    packed = replace(packed, '    double score[9], freqs[9];',
                     '    PackedRotation rotation[pilot / 4];\n'
                     '    pack_rotation(hr, hiq, rotation, pilot);\n'
                     '    LateCorrelation late[9][frames][4];\n'
                     '    correlate_late(x, hr, hiq, epoch - 4, late);\n'
                     '    double score[9], freqs[9];')
    begin = packed.index('                #pragma omp simd reduction(+:a,c,power)')
    end = packed.index('                zr[f][b]=a;', begin)
    packed = packed[:begin] + '''                if (b < 4) {
                    correlate_block(x + 2 * (offset + b * block), rotation + b * block / 4,
                                    block, &a, &c, &power);
                } else {
                    LateCorrelation z = late[i][f][b - 4];
                    a = z.real;
                    c = z.imag;
                    power = z.power;
                }
''' + packed[end:]
    signature_end = original.index('{') + 1
    dispatched = original[:signature_end] + '''
    if (epoch >= 4 && epoch < period - 4 && __builtin_cpu_supports("avx2"))
        return delay_refine_packed(x, h, epoch, hz, lo, hi, out);''' + original[signature_end:]
    return text[:start] + packed + '\n' + dispatched


def clamp_residual(text):
    return replace(text, '    return (int16_t)lrint(fmin(32767., fmax(-32768., value)));',
                   '    if (!(value >= -32768.)) return -32768;\n'
                   '    if (value > 32767.) return 32767;\n    return (int16_t)lrint(value);')


def omit_integer_control(text):
    return replace(text, 'w->glrt_exact, w->glrt_control, w->correlations[0], w->correlations[1]);',
                   'w->glrt_exact, w->glrt_control, w->correlations[0],\n'
                   '                           control ? w->correlations[1] : NULL);')


def exact_integer_only(text):
    original = '''                    accumulate(corrected, exact + offset, control + offset, t,
                               exact_lanes, control_lanes);'''
    alternate = '''                    if (control_out) {
                        accumulate(corrected, exact + offset, control + offset, t,
                                   exact_lanes, control_lanes);
                    } else {
                        int k = t % lanes;
                        complex64x2 term = mul(exact[offset + t], corrected);
                        exact_lanes[k] = t < lanes ? term : add(exact_lanes[k], term);
                    }'''
    text = replace(text, original, alternate)
    return replace(text, '                control_out[index * symbols + s] = pairwise_sum(control_lanes);',
                   '                if (control_out)\n'
                   '                    control_out[index * symbols + s] = pairwise_sum(control_lanes);')


PROFILE_SIGNATURES = {
    "timing_first_receiver.c": [
        ("static void input(", "INPUT"), ("static void principal_modes(", "MODES"),
        ("static void find_times(", "TIME_SEARCH"), ("static int find_carriers(", "CARRIER_SEARCH"),
        ("static int gate(", "GATE"), ("int timing_first_detect(", "TIMING"),
    ],
    "delay_product_kernel.c": [("int delay_decimate(", "DECIMATE"), ("int delay_refine(", "REFINE")],
    "two_carrier_receiver.c": [("static int measure(", "MEASURE")],
    "pilot_cancel.c": [("int pilot_cancel(", "CANCEL")],
    "portable_verifier.c": [("int portable_verifier_load(", "VERIFY_LOAD"),
                            ("int portable_verifier_factor(", "VERIFY")],
}


def profile_source(text, signatures):
    for signature, name in signatures:
        offset = text.index('{', text.index(signature)) + 1
        text = text[:offset] + f'\n    PROFILE({name});' + text[offset:]
    return '#define _POSIX_C_SOURCE 200809L\n#include "receiver_profile.h"\n' + text


def build(output, *, fftw=True, crop=True, early_gate=True, avx2=False, fma=True, reuse=True,
          pack_refine=True, profile=False, tracking=False, projection=False, shortlist_audit=False,
          short_aperture=False, adjacent_primary=False, pack_stencil=False):
    if (avx2 or fma or pack_stencil) and platform.machine() != "x86_64":
        raise ValueError("the instruction-set optimizations require x86-64")
    if sum((tracking, projection, shortlist_audit, short_aperture, adjacent_primary)) > 1:
        raise ValueError("build each experimental scout or audit separately")
    if adjacent_primary and not fftw:
        raise ValueError("the historical adjacent-symbol scout requires FFTW")
    recipe = json.loads((PINNED / "build.json").read_bytes())
    for name, expected in recipe["source_digests"].items():
        if hashlib.sha256((PINNED / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f"ALGO08v2 source digest mismatch for {name}")
    args = recipe["args"]
    first_source = next(i for i, arg in enumerate(args) if arg.endswith(".c"))
    compile_args = [arg for arg in args[:first_source] if arg not in ("-shared", "-Wl,--gc-sections")]
    source_paths = [PINNED / arg for arg in args[first_source:] if arg.endswith(".c")]
    if profile:
        source_paths.append(HERE / "receiver_profile.c")
    if tracking:
        from .receiver_tracking_overlay import measure_overlay, timing_overlay
    if projection:
        from .receiver_projection_overlay import measure_overlay, timing_overlay
    if shortlist_audit:
        from .receiver_shortlist_overlay import measure_overlay, timing_overlay
    if short_aperture:
        from .receiver_aperture_overlay import kernel_overlay, timing_overlay
    if adjacent_primary:
        from .receiver_adjacent_overlay import fold_overlay, measure_overlay, timing_overlay

        source_paths.append(HERE.parent / "differential_runtime_fft.c")
    overlay = tracking or projection or shortlist_audit or adjacent_primary
    with TemporaryDirectory(dir=output.parent) as work:
        scratch = Path(work)
        objects = []
        for path in source_paths:
            options = []
            source = path.read_text()
            if adjacent_primary and path.name == "differential_runtime_fft.c":
                source = fold_overlay(source)
            if path.name == "timing_first_receiver.c":
                if fftw:
                    source = fftw_timing(source, crop)
                if early_gate:
                    source = group_gate(source)
                if overlay or short_aperture:
                    source = timing_overlay(source)
            if overlay and path.name == "two_carrier_receiver.c":
                source = measure_overlay(source)
            if reuse:
                if path.name == "delay_product_kernel.c" and platform.machine() == "x86_64":
                    source = paired_fir(source)
                    if pack_refine and not avx2:
                        source = paired_refine(source)
                if path.name == "pilot_cancel.c":
                    source = clamp_residual(source)
                if path.name == "refine_bank.c":
                    source = exact_integer_only(source)
                if path.name == "portable_verifier.c":
                    source = omit_integer_control(source)
            if pack_stencil:
                if path.name == "refine_bank.c":
                    source += '\n#include "receiver_stencil_kernel.inc"\n'
                if path.name == "portable_verifier.c":
                    from .receiver_stencil_overlay import verifier_overlay

                    source = verifier_overlay(source)
            if path.name in ("timing_first_receiver.c", "delay_product_kernel.c") and avx2:
                options.append("-mavx2")
            if short_aperture and path.name == "delay_product_kernel.c":
                source = kernel_overlay(source)
            if path.name == "refine_bank.c" and fma:
                options.append("-mfma")
            if path.name == "receiver_profile.c":
                options.append("-D_POSIX_C_SOURCE=200809L")
            if profile and path.name in PROFILE_SIGNATURES:
                source = profile_source(source, PROFILE_SIGNATURES[path.name])
            copy = scratch / path.name
            copy.write_text(source)
            obj = copy.with_suffix(".o")
            subprocess.run([recipe["cc"], *compile_args, *options, "-I", path.parent, "-I", HERE,
                            "-c", copy, "-o", obj], cwd=PINNED, check=True)
            objects.append(obj)
        staged = scratch / "receiver.so"
        libraries = ["-lfftw3f", "-pthread"] if fftw else []
        subprocess.run([recipe["cc"], "-shared", "-Wl,--gc-sections", *objects, *libraries,
                        "-lm", "-o", staged], check=True)
        os.replace(staged, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--fftw", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--crop", action=argparse.BooleanOptionalAction, default=True,
                        help="use shorter circular correlation lengths with FFTW")
    parser.add_argument("--early-gate", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--avx2", action=argparse.BooleanOptionalAction, default=False,
                        help="change timing/refinement SIMD accumulation order")
    parser.add_argument("--fma", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--reuse", action=argparse.BooleanOptionalAction, default=True,
                        help="use the paired FIR, direct residual clamp and exact-only integer correlations")
    parser.add_argument("--pack-refine", action=argparse.BooleanOptionalAction, default=True,
                        help="pack coarse carrier refinement accumulators while retaining the released order")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--tracking", action="store_true")
    parser.add_argument("--projection", action="store_true")
    parser.add_argument("--shortlist-audit", action="store_true")
    parser.add_argument("--short-aperture", action="store_true")
    parser.add_argument("--adjacent-primary", action="store_true")
    parser.add_argument("--pack-stencil", action="store_true")
    args = parser.parse_args()
    build(args.output, fftw=args.fftw, crop=args.crop, early_gate=args.early_gate, avx2=args.avx2,
          fma=args.fma, reuse=args.reuse, pack_refine=args.pack_refine,
          profile=args.profile, tracking=args.tracking, projection=args.projection,
          shortlist_audit=args.shortlist_audit, short_aperture=args.short_aperture,
          adjacent_primary=args.adjacent_primary, pack_stencil=args.pack_stencil)


if __name__ == "__main__":
    main()
