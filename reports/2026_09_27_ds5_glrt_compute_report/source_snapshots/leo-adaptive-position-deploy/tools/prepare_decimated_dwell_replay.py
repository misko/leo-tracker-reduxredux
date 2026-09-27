"""Build and prepare fixed-point 10M-to-2.5M saved-IQ development replay."""

import argparse
import hashlib
import json
import struct
import subprocess
from pathlib import Path

import numpy as np

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.investigate_adaptive_decision_budget import control_iq
from tools.native_presence import NATIVE, ROOT


def coefficients(kind):
    def fir(n, cutoff, beta=7.5):
        x = np.arange(n) - (n - 1) / 2
        h = 2 * cutoff * np.sinc(2 * cutoff * x) * np.kaiser(n, beta)
        q = np.rint(h / h.sum() * 32768).astype(np.int64)
        q[n // 2] += 32768 - q.sum()
        assert np.max(np.abs(q)) < 32768 and np.sum(np.abs(q)) < 65536
        return q.astype("<i2")

    if kind == "cascade":
        return fir(19, 0.25), fir(81, 0.20)
    if kind == "compact":
        return fir(15, 0.25, 6.75), fir(47, 0.20, 5.75)
    if kind == "recursive":
        return fir(15, 0.25, 6.75), np.array(
            [109, 600, 1900, 4238, 7287, 10075, 11439, 10775, 8413, 5406, 2802, 1136, 339, 67, 7],
            dtype="<i2",
        )
    if kind == "direct":
        return np.empty(0, dtype="<i2"), fir(161, 0.10)
    raise ValueError("unknown filter candidate")


def multirate_coefficients(source_rate_hz):
    """Reproduce the sealed direct FIR for a 15/20M to 2.5M reduction."""
    geometry = {
        15_000_000: (201, 1.0 / 15.0),
        20_000_000: (257, 1.0 / 20.0),
    }
    try:
        taps, cutoff = geometry[source_rate_hz]
    except KeyError as error:
        raise ValueError("multirate source must be 15 or 20 MS/s") from error
    x = np.arange(taps) - (taps - 1) / 2
    h = 2 * cutoff * np.sinc(2 * cutoff * x) * np.kaiser(taps, 8.6)
    q = np.rint(h / h.sum() * 32768).astype(np.int64)
    q[taps // 2] += 32768 - q.sum()
    assert np.max(np.abs(q)) < 32768 and np.sum(np.abs(q)) < 65536
    return q.astype("<i2")


def multirate_reference(iq, source_rate_hz):
    """Independent causal Q15 reference for one reset 15/20M dwell."""
    factor = source_rate_hz // 2_500_000
    h = multirate_coefficients(source_rate_hz).astype(np.int64)
    values = np.stack(
        [np.convolve(iq[:, channel].astype(np.int64), h)[: len(iq) : factor] for channel in (0, 1)],
        axis=1,
    )
    return np.clip((values + 16384) // 32768, -32768, 32767).astype("<i2")


def recursive_denominator():
    # SciPy 1.16.2 ellipord/ellip: fs=5 MHz, pass=.8, stop=1.25,
    # ripple=.004 dB, rejection=71.5 dB. Polyphase denominator obtained by
    # multiplying each A(z) by A(-z), then retaining the even powers.
    return np.array(
        [
            [-0.18529008328914642, 0],
            [-0.10079888999462128, 0.08974389731884003],
            [0.47597214579582214, 0.31046468019485474],
            [1.0251710414886475, 0.7138981223106384],
        ],
        dtype="<f4",
    )


def reference(iq, h1, h2, recursive=False):
    def stage(x, h, factor):
        values = np.stack(
            [
                np.convolve(x[:, c].astype(np.int64), h.astype(np.int64))[: len(x) : factor]
                for c in (0, 1)
            ],
            axis=1,
        )
        return np.clip((values + 16384) // 32768, -32768, 32767).astype("<i2")

    if recursive:
        first = stage(iq, h1, 2)
        pre = (
            np.stack(
                [
                    np.convolve(first[:, c].astype(np.int64), h2.astype(np.int64))[: len(first) : 2]
                    for c in (0, 1)
                ],
                axis=1,
            )
            / 16384
        )
        # Independent double-precision impulse convolution, not the C direct
        # recurrence. For these fixed stable poles the discarded tail after
        # 1024 output samples is far below one CI16 LSB at full input scale.
        impulse = np.zeros(1024)
        impulse[0] = 1
        for a, b in recursive_denominator().astype(np.float64):
            previous, older = 0.0, 0.0
            for index, value in enumerate(impulse):
                current = value - a * previous - b * older
                impulse[index] = current
                older, previous = previous, current
        assert np.max(np.abs(impulse[-128:])) < 1e-50
        size = 1 << (len(pre) + len(impulse) - 1).bit_length()
        filtered = np.fft.irfft(
            np.fft.rfft(pre, size, axis=0) * np.fft.rfft(impulse, size)[:, None], size, axis=0
        )[: len(pre)]
        return np.clip(np.floor(filtered + 0.5), -32768, 32767).astype("<i2")
    if len(h1):
        return stage(stage(iq, h1, 2), h2, 2)
    return stage(iq, h2, 4)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def emit_compact_kernel(output):
    """Unroll sealed compact FIR taps; no coefficient load/branch per tap."""
    lines = ["/* Generated from coefficients('compact'); do not edit. */"]
    for h in coefficients("compact"):
        n = len(h)
        offsets = [i for i, value in enumerate(h) if value]
        lines += [
            f"static const int16_t compact_coefficients_{n}[{n}]={{"
            + ",".join(str(int(v)) for v in h)
            + "};"
        ]
        lines += [
            f"static void compact_{n}(const struct fir *f,const int16_t *x,",
            "size_t count,int16_t *out) {",
            "for (size_t m=0;m<count/2;m+=16) {",
            "int32x4_t a=vdupq_n_s32(0),b=a,c=a,d=a,e=a,g=a,j=a,l=a;",
        ]
        for index, offset in enumerate(offsets):
            if index % 4 == 0:
                lines += [f"int16x4_t h{index // 4}=vld1_s16(f->h+{index});"]
            lines += ["{", f"const int32_t *p=(const int32_t *)(x+2*((ptrdiff_t)(2*m)-{offset}));"]
            for pair, shift in (("ab", 0), ("cd", 8), ("eg", 16), ("jl", 24)):
                lines += [
                    "{",
                    f"int16x8_t v=vreinterpretq_s16_s32(vld2q_s32(p+{shift}).val[0]);",
                    f"{pair[0]}=vmlal_lane_s16({pair[0]},vget_low_s16(v),"
                    f"h{index // 4},{index % 4});",
                    f"{pair[1]}=vmlal_lane_s16({pair[1]},vget_high_s16(v),"
                    f"h{index // 4},{index % 4});",
                    "}",
                ]
            lines += ["}"]
        for pair, offset in (("ab", 0), ("cd", 8), ("eg", 16), ("jl", 24)):
            lines += [
                f"vst1q_s16(out+2*m+{offset},vcombine_s16(vqrshrn_n_s32({pair[0]},15),vqrshrn_n_s32({pair[1]},15)));"
            ]
        lines += ["}", "}"]
    output.write_text("\n".join(lines) + "\n")


def build(
    output,
    compiler="cc",
    fftw_prefix=None,
    shared=False,
    sanitize=False,
    fp32=False,
    specialized=False,
    phased=False,
    recursive_pairs=False,
    fftw_float_prefix=None,
    tile=2048,
):
    sources = [
        NATIVE / name
        for name in (
            "presence.c",
            "fft.c",
            "window_rank.c",
            "dwell.c",
            "decision_decimator.c",
            "host_decision.c",
        )
    ]
    if not shared:
        sources.append(ROOT / "tools/decimated_dwell_replay.c")
    if fftw_float_prefix:
        sources.append(NATIVE / "decision_decimator_fft.c")
    dependencies = [
        *NATIVE.glob("*.[ch]"),
        NATIVE / "host_decision_coefficients.inc",
        ROOT / "runtime/scanner-glrt/algorithm.json",
        ROOT / "src/leo/analysis/starlink/_native_acquisition_grid.inc",
        ROOT / "tools/decimated_dwell_replay.c",
        Path(__file__),
    ]
    flags = json.loads((ROOT / "runtime/scanner-glrt/algorithm.json").read_text())["native_defines"]
    command = [
        compiler,
        "-std=c11",
        "-O3",
        "-fno-math-errno",
        "-Wall",
        "-Wextra",
        "-Werror",
        *flags,
    ]
    if fftw_prefix:
        command += [
            "-mcpu=cortex-a9",
            "-mfpu=neon",
            "-mfloat-abi=hard",
            "-DLEO_PRESENCE_FFTW=1",
            f"-I{fftw_prefix / 'include'}",
        ]
        dependencies += [fftw_prefix / "include/fftw3.h", fftw_prefix / "lib/libfftw3.so"]
    if shared:
        command += ["-shared", "-fPIC"]
    if fp32:
        command += ["-DLEO_DECIMATOR_FP32=1"]
    if phased:
        command += ["-DLEO_DECIMATOR_PHASED=1"]
    if recursive_pairs:
        command += ["-DLEO_DECIMATOR_RECURSIVE_PAIRS=1"]
    if fftw_float_prefix:
        if fp32 or recursive_pairs:
            raise ValueError("select one floating-point experiment")
        command += ["-DLEO_DECIMATOR_FFT=1", f"-I{fftw_float_prefix / 'include'}"]
        dependencies += [
            fftw_float_prefix / "include/fftw3.h",
            fftw_float_prefix / "lib/libfftw3f.a",
        ]
    if tile not in (1024, 2048):
        raise ValueError("unsupported tile")
    command += [f"-DLEO_DECIMATOR_TILE={tile}"]
    if specialized:
        generated = output.parent / "decision_decimator_compact.inc"
        emit_compact_kernel(generated)
        dependencies.append(generated)
        command += ["-DLEO_DECIMATOR_COMPACT=1", f"-I{output.parent}"]
    if sanitize:
        command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
    before = {str(p): sha(p) for p in dependencies}
    command += [str(p) for p in sources]
    if fftw_prefix:
        command += [f"-L{fftw_prefix / 'lib'}", "-lfftw3"]
    if fftw_float_prefix:
        command += [str(fftw_float_prefix / "lib/libfftw3f.a")]
    command += ["-lm", "-o", str(output)]
    if output.exists():
        raise FileExistsError(output)
    subprocess.run(command, check=True)
    assert before == {str(p): sha(p) for p in dependencies}
    output.with_suffix(output.suffix + ".build.json").write_text(
        json.dumps(
            dict(command=command, sources_sha256=before, binary_sha256=sha(output)), indent=2
        )
        + "\n"
    )
    return output


def prepare(source, output, kind):
    """Reuse the frozen 16-case development pack; this is not new holdout data."""
    h1, h2 = coefficients(kind)
    with source.open("rb") as inp, output.open("xb") as sink:
        magic, rate, n, cases = struct.unpack("<4sIII", inp.read(16))
        if (magic, rate, n) != (b"LPG1", 5000000, 6667) or not 1 <= cases <= 64:
            raise ValueError("unexpected source pack")
        inp.seek(129 * 4 + 4 * n * 16, 1)
        sink.write(
            struct.pack(
                "<4sIIIII",
                b"LDR1" if kind == "recursive" else b"LDD1",
                2500000,
                3333,
                cases,
                len(h1),
                len(h2),
            )
        )
        sink.write(h1.tobytes() + h2.tobytes())
        if kind == "recursive":
            sink.write(recursive_denominator().tobytes())
        for edge in ("lower", "upper"):
            for roll in (0, 17):
                sink.write(
                    qin_edge_pilot_frame(2500000, edge, symbol_roll=roll).astype("<c16").tobytes()
                )
        rows = []
        for _ in range(cases):
            header = inp.read(16)
            iq = np.frombuffer(inp.read(4800000), dtype="<i2").reshape(1200000, 2)
            inp.seek(400000, 1)
            expected = reference(iq, h1, h2, recursive=kind == "recursive")
            sink.write(header + iq.tobytes() + expected.tobytes())
            case, rx, edge, visit = struct.unpack("<IIII", header)
            rows.append(
                dict(
                    case=case,
                    rx=rx,
                    edge=edge,
                    visit=visit,
                    iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
                )
            )
        if inp.read(1):
            raise ValueError("trailing source pack data")
    output.with_suffix(".json").write_text(
        json.dumps(
            dict(
                kind=kind,
                source_pack_sha256=sha(source),
                pack_sha256=sha(output),
                cases=rows,
                coefficients_q15=[h1.tolist(), h2.tolist()],
                group_delay_native_samples=None
                if kind == "recursive"
                else (len(h1) - 1) / 2 + len(h2) - 1
                if len(h1)
                else (len(h2) - 1) / 2,
                rounding="nearest, ties toward positive infinity; saturation at each stage",
                scope="development replay; zero history; no RF or boundary coverage qualification",
            ),
            indent=2,
        )
        + "\n"
    )


def prepare_controls(output, kind):
    """Freeze synthetic pilot/negative and full-scale arithmetic controls."""
    h1, h2 = coefficients(kind)
    cases = [(edge, "pilot", window) for edge in ("lower", "upper") for window in range(6)]
    cases += [
        (edge, name, 0) for edge in ("lower", "upper") for name in ("noise", "tone", "alias_tone")
    ]
    cases += [("lower", name, 0) for name in ("full_scale", "positive_dc", "negative_dc", "zero")]
    rows = []
    with output.open("xb") as sink:
        sink.write(
            struct.pack(
                "<4sIIIII",
                b"LDR1" if kind == "recursive" else b"LDD1",
                2500000,
                3333,
                len(cases),
                len(h1),
                len(h2),
            )
        )
        sink.write(h1.tobytes() + h2.tobytes())
        if kind == "recursive":
            sink.write(recursive_denominator().tobytes())
        for edge in ("lower", "upper"):
            for roll in (0, 17):
                sink.write(
                    qin_edge_pilot_frame(2500000, edge, symbol_roll=roll).astype("<c16").tobytes()
                )
        for index, (edge, name, window) in enumerate(cases):
            if name == "full_scale":
                iq = np.random.default_rng(911).integers(-32768, 32768, (1200000, 2), dtype="int16")
            elif name in ("positive_dc", "negative_dc", "zero"):
                value = {"positive_dc": 32767, "negative_dc": -32768, "zero": 0}[name]
                iq = np.full((1200000, 2), value, dtype="int16")
            else:
                iq = control_iq(edge, name, window, 100 + window if name == "pilot" else 301)
            expected = reference(iq, h1, h2, recursive=kind == "recursive")
            sink.write(struct.pack("<IIII", index, index % 2, int(edge == "upper"), index))
            sink.write(iq.tobytes() + expected.tobytes())
            rows.append(
                dict(
                    case=index,
                    edge=edge,
                    kind=name,
                    window=window,
                    expected_positive=name == "pilot",
                    iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),
                )
            )
    output.with_suffix(".json").write_text(
        json.dumps(
            dict(
                kind=kind,
                pack_sha256=sha(output),
                cases=rows,
                scope="synthetic smoke and arithmetic controls; not false-alarm calibration",
            ),
            indent=2,
        )
        + "\n"
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    inputs = p.add_mutually_exclusive_group()
    inputs.add_argument("--source-pack", type=Path)
    inputs.add_argument("--controls", action="store_true")
    p.add_argument(
        "--kind", choices=("cascade", "direct", "compact", "recursive"), default="cascade"
    )
    p.add_argument("--compiler", default="cc")
    p.add_argument("--fftw-prefix", type=Path)
    p.add_argument("--fftw-float-prefix", type=Path)
    p.add_argument("--sanitize", action="store_true")
    p.add_argument("--fp32", action="store_true")
    p.add_argument("--specialized", action="store_true")
    p.add_argument("--phased", action="store_true")
    p.add_argument("--recursive-pairs", action="store_true")
    p.add_argument("--tile", type=int, choices=(1024, 2048), default=2048)
    args = p.parse_args()
    args.output = args.output.resolve()
    if any(args.output.is_relative_to(Path(root)) for root in ("/mnt/qnap01", "/srv/bulk/leo")):
        p.error("output must be outside corpus storage")
    args.output.mkdir(parents=True, exist_ok=False)
    build(
        args.output / "replay",
        args.compiler,
        args.fftw_prefix,
        sanitize=args.sanitize,
        fp32=args.fp32,
        specialized=args.specialized,
        phased=args.phased,
        recursive_pairs=args.recursive_pairs,
        fftw_float_prefix=args.fftw_float_prefix,
        tile=args.tile,
    )
    if args.source_pack:
        prepare(args.source_pack, args.output / "workload.pack", args.kind)
    elif args.controls:
        prepare_controls(args.output / "controls.pack", args.kind)


if __name__ == "__main__":
    main()
