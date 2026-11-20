"""Build the full raw detector and retained-seed verifier from pinned C sources."""

import argparse
import hashlib
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
REVISION = "234490f2b"
VARIANTS = Path("tools/pipeline_eval/variants")
QUALIFICATION = Path("tools/pipeline_eval/qualification")
KERNEL = Path("native/adaptive/detector/kernel/private")
NAMES = (
    "portable_verifier.c",
    "portable_verifier.h",
    "portable_fine.c",
    "portable_fine.h",
    "fine_search.c",
    "conditioned_cfo_bank.c",
    "refine_bank.c",
    "portable_coarse.c",
    "portable_coarse.h",
    "portable_coarse_qin.h",
)
PATHS = (
    *(VARIANTS / name for name in NAMES),
    *(QUALIFICATION / name for name in ("portable_coarse_cli.c", "portable_verifier_cli.c")),
    KERNEL / "fft_full.c",
    KERNEL / "native_presence/fft.h",
)
FLAGS = (
    "-std=c11",
    "-O3",
    "-Wall",
    "-Wextra",
    "-Werror",
    "-ffp-contract=off",
    "-fopenmp-simd",
    "-static",
    "-fstack-usage",
    "-DLEO_PRESENCE_ITERATIVE_FFT=1",
    "-fno-math-errno",
)
ARM_CC = Path.home() / "gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc"
TARGETS = {
    "x86": ("cc", ("-march=x86-64-v3",), ()),
    "aarch64": ("aarch64-linux-gnu-gcc", ("-march=armv8-a",), ("qemu-aarch64",)),
    "cortex-a9": (
        str(ARM_CC),
        ("-mcpu=cortex-a9", "-mfpu=neon", "-mfloat-abi=hard"),
        ("qemu-arm", "-cpu", "cortex-a9"),
    ),
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def replace(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Pinned C source changed near {old!r}")
    return source.replace(old, new, 1)


def between(source, first, last, new):
    start = source.index(first)
    end = source.index(last, start)
    return source[:start] + new + source[end:]


def compact_verifier(source):
    for before, after in (
        ('#include "fft.h"', '#include "fft.h"\n#include "c_fine_memory.h"'),
        ("void conditioned_moments(const double *", "void conditioned_moments(const int16_t *"),
        ("void conditioned_single(const double *", "void conditioned_single(const int16_t *"),
        (
            "void correlated_integer(const GlrtComplex *",
            "void correlated_integer(const CompactIQ *",
        ),
        (
            "void correlated_fractional(const GlrtComplex *",
            "void correlated_fractional(const CompactIQ *",
        ),
        (
            "PortableFineComplex fine[samples]; GlrtComplex glrt[samples]; double data[2*samples]",
            "CompactIQ fine[samples]; CompactIQ glrt[samples]; int16_t data[2*samples]",
        ),
        (
            "GlrtComplex glrt_rotation[max_frames * aperture];",
            "GlrtComplex glrt_rotation[aperture], fractional_rotation[aperture];\n"
            "    double integer_hz;",
        ),
        (
            "int32_t indices[max_frames * aperture], weight_row[max_frames * aperture];",
            "int32_t indices[aperture], weight_row[aperture];",
        ),
        (
            "    portable_fine_prepare(&w->fine);",
            "    portable_fine_prepare(&w->fine);\n    w->integer_hz = NAN;",
        ),
        ("w->iq.fine[sample] = (PortableFineComplex)", "w->iq.fine[sample] = (CompactIQ)"),
        (
            "static inline PortableFineComplex rotate",
            "static inline double compact_energy(CompactIQ z) {\n"
            "    double re = z.r, im = z.i;\n    return re*re + im*im;\n}\n"
            "static inline PortableFineComplex rotate",
        ),
        ("energy(w->iq.fine[start+j])", "compact_energy(w->iq.fine[start+j])"),
        ("static int equivalent(", '#include "c_fine_memory_held.inc"\n\nstatic int equivalent('),
        (
            "        out[i].verify = pilots(w, seed->epoch, out[i].acquired_hz, w->exact, 3);\n"
            "        out[i].verify_control = pilots(w, seed->epoch, "
            "out[i].acquired_hz, w->control, 3);",
            "        held_pilots(w, seed->epoch, out[i].acquired_hz, "
            "&out[i].verify, &out[i].verify_control);",
        ),
        ("static int glrt(", '#include "c_fine_memory_fractional.inc"\n\nstatic int glrt('),
        (
            "        for (int k = 0; k < aperture; ++k) {\n"
            "            PortableFineComplex z = rotate(-tau*cfo*(first+k)/rate);\n"
            "            w->glrt_rotation[k] = (GlrtComplex){z.r,z.i};\n        }",
            "        if (w->integer_hz != cfo) {\n"
            "            for (int k = 0; k < aperture; ++k) {\n"
            "                PortableFineComplex z = rotate(-tau*cfo*(first+k)/rate);\n"
            "                w->glrt_rotation[k] = (GlrtComplex){z.r,z.i};\n"
            "            }\n            w->integer_hz = cfo;\n        }",
        ),
    ):
        source = replace(source, before, after)
    return between(
        source,
        "    } else {\n        double old_fraction",
        "    int best, unused;",
        "    } else if (fractional_correlations(w, frames, starts, cfo, offset)) return -1;\n",
    )


def compact_sources(source):
    header = source["portable_fine.h"]
    header = replace(header, "/* Fixed", '#include "c_fine_memory.h"\n\n/* Fixed')
    header = replace(
        header,
        "scratch[2 * PORTABLE_FINE_FFT]",
        "scratch[PORTABLE_FINE_FFT + 25*PORTABLE_FINE_MAX_BINS + 160*5]",
    )
    signature = "const PortableFineComplex *samples"
    fine = replace(source["portable_fine.c"], signature, "const CompactIQ *samples")
    fine = replace(
        fine,
        "                PortableFineComplex received = samples[start + symbol + i];",
        "                CompactIQ raw = samples[start + symbol + i];\n"
        "                PortableFineComplex received = {raw.r, raw.i};",
    )
    fine = replace(fine, "    memset(workspace->scratch, 0, sizeof(workspace->scratch));\n", "")
    moments = source["conditioned_cfo_bank.c"].replace(
        "double *restrict iq", "int16_t *restrict iq"
    )
    moments = replace(moments, "moments(const double *iq", "moments(const int16_t *iq")
    moments = moments.replace("const double *row = iq", "const int16_t *row = iq")
    refine = '#include "c_fine_memory.h"\n' + source["refine_bank.c"]
    refine = replace(
        refine, "interpolate(const complex64x2 *values", "interpolate(const CompactIQ *values"
    )
    refine = replace(
        refine,
        "values[t].re * weights[t], values[t].im * weights[t]",
        "values[t].r * weights[t], values[t].i * weights[t]",
    )
    refine = replace(
        refine, "complex64x2 sample = values[t + k];", "CompactIQ sample = values[t + k];"
    )
    refine = replace(refine, "sample.re * w", "sample.r * w")
    refine = replace(refine, "sample.im * w", "sample.i * w")
    refine = refine.replace("const complex64x2 *restrict iq", "const CompactIQ *restrict iq")
    refine = replace(refine, "const complex64x2 *received = iq", "const CompactIQ *received = iq")
    refine = replace(
        refine,
        "                    complex64x2 corrected = mul(received[offset + t], phase[offset + t]);",
        "                    CompactIQ raw = received[offset + t];\n"
        "                    complex64x2 corrected = mul((complex64x2){raw.r, raw.i}, "
        "phase[offset+t]);",
    )
    return source | {
        "portable_fine.h": replace(header, signature, "const CompactIQ *samples"),
        "portable_fine.c": fine,
        "fine_search.c": source["fine_search.c"].split("#define PASS", 1)[0]
        + '#include "c_fine_memory_fft.inc"\n',
        "conditioned_cfo_bank.c": moments,
        "refine_bank.c": refine,
        "portable_verifier.c": compact_verifier(source["portable_verifier.c"]),
    }


PROFILE = """static long memory_peak(void) {
    FILE *status = fopen("/proc/self/status", "r");
    if (!status) return -1;
    char line[128];
    long kib = -1;
    while (fgets(line, sizeof(line), status)) if (sscanf(line, "VmHWM: %ld kB", &kib) == 1) break;
    fclose(status);
    return kib;
}

"""


def time_detector(source):
    source = replace(source, "int main(", PROFILE + "int main(")
    source = replace(
        source,
        "    const uint32_t one=1;",
        "    const uint32_t one=1;\n"
        "    const uint64_t start_cpu=ns(CLOCK_PROCESS_CPUTIME_ID), "
        "start_wall=ns(CLOCK_MONOTONIC);",
    )
    source = replace(
        source,
        '"\\"input_bytes\\":%zu}\\n",setup_cpu,setup_wall,usage.ru_maxrss,',
        '"\\"input_bytes\\":%zu,\\"process_cpu_ns\\":%" PRIu64 ",\\"elapsed_ns\\":%" PRIu64\n'
        '            ",\\"vm_hwm_kib\\":%ld}\\n",setup_cpu,setup_wall,usage.ru_maxrss,',
    )
    return replace(
        source,
        "portable_verifier_workspace_bytes(),iq_bytes);",
        "portable_verifier_workspace_bytes(),iq_bytes,ns(CLOCK_PROCESS_CPUTIME_ID)-start_cpu,\n"
        "            ns(CLOCK_MONOTONIC)-start_wall,memory_peak());",
    )


def build(work, target, arm, driver="full", profile=False):
    folder = work / f"{target}-{arm}-{driver}{'-profile' if profile else ''}"
    folder.mkdir(parents=True, exist_ok=True)
    sources = {
        path: subprocess.check_output(["git", "show", f"{REVISION}:{path}"], cwd=ROOT)
        for path in PATHS
    }
    variants = {
        p.name: contents.decode() for p, contents in sources.items() if p.parent == VARIANTS
    }
    if arm == "compact":
        variants = compact_sources(variants)
    for path, contents in sources.items():
        dest = folder / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        if path.parent == VARIANTS:
            contents = variants[path.name].encode()
        if path.name == "portable_coarse_cli.c":
            contents = time_detector(contents.decode()).encode()
        dest.write_bytes(contents)
    extras = {}
    if arm == "compact":
        for path in sorted((ROOT / VARIANTS).glob("c_fine_memory*")):
            extras[str(path.relative_to(ROOT))] = digest(path.read_bytes())
            (folder / VARIANTS / path.name).write_bytes(path.read_bytes())
    cc, arch, _ = TARGETS[target]
    names = [
        name
        for name in NAMES
        if name.endswith(".c") and (driver == "full" or name != "portable_coarse.c")
    ]
    cli = QUALIFICATION / (
        "portable_coarse_cli.c" if driver == "full" else "portable_verifier_cli.c"
    )
    command = [
        cc,
        *FLAGS,
        *arch,
        *(("-pg",) if profile else ()),
        "-I",
        str(KERNEL / "native_presence"),
        str(cli),
        *(str(VARIANTS / name) for name in names),
        str(KERNEL / "fft_full.c"),
        "-lm",
        "-o",
        "detector",
    ]
    subprocess.run(
        command, cwd=folder, check=True, timeout=80, env=os.environ | {"TMPDIR": str(folder)}
    )
    binary = folder / "detector"
    stacks = {}
    for path in sorted(folder.glob("*.su")):
        for line in path.read_text().splitlines():
            function, size, kind = line.split("\t")
            stacks[function] = [int(size), kind]
    return binary, dict(
        revision=subprocess.check_output(
            ["git", "rev-parse", REVISION], cwd=ROOT, text=True
        ).strip(),
        compiler=subprocess.check_output([cc, "--version"], text=True).splitlines()[0],
        command=command,
        sha256=digest(binary.read_bytes()),
        stack=stacks,
        stock_sources={str(path): digest(contents) for path, contents in sources.items()},
        compiled_sources={str(path): digest((folder / path).read_bytes()) for path in sources},
        extra_sources=extras,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument("arm", choices=("stock", "compact"))
    parser.add_argument("--driver", choices=("full", "stage"), default="full")
    parser.add_argument("--profile", action="store_true")
    args = parser.parse_args()
    print(build(args.work.resolve(), args.target, args.arm, args.driver, args.profile)[0])
