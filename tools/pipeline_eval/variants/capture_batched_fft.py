"""Lower-precision batched FFT proposals for the complete original coarse grid."""

import subprocess

from . import capture_fft
from .wide_regional import replace


def fft_bank(source):
    # Batch carrier inverses per anchor/block. Reuse the forward FFT and every
    # original anchor, admissible frame, normalizer, and lattice cell.
    source = source.replace("fftw_", "fftwf_")
    source = replace(
        source,
        "fftwf_complex *output = fftwf_alloc_complex(fft_length);",
        "fftwf_complex *inverse_input = fftwf_alloc_complex((size_t)nf * fft_length);\n"
        "    fftwf_complex *output = fftwf_alloc_complex((size_t)nf * fft_length);",
    )
    source = replace(
        source,
        "!filters || !input || !spectrum || !output",
        "!filters || !input || !spectrum || !inverse_input || !output",
    )
    source = replace(
        source,
        "inverse = fftwf_plan_dft_1d(fft_length, input, output, FFTW_BACKWARD, FFTW_ESTIMATE);",
        "const int length = fft_length;\n"
        "    inverse = fftwf_plan_many_dft(1, &length, nf, inverse_input, NULL, 1, fft_length,\n"
        "        output, NULL, 1, fft_length, FFTW_BACKWARD, FFTW_ESTIMATE);",
    )
    source = replace(
        source,
        "const double xr = spectrum[j][0], xi = spectrum[j][1];\n"
        "                    const double hr = filter[j][0], hi = filter[j][1];\n"
        "                    input[j][0] = xr * hr - xi * hi;\n"
        "                    input[j][1] = xr * hi + xi * hr;\n"
        "                }\n"
        "                fftwf_execute(inverse);\n"
        "                ++inverse_calls;\n"
        "                double *row = k->scores + (size_t)f * ne;",
        "const float xr = spectrum[j][0], xi = spectrum[j][1];\n"
        "                    const float hr = filter[j][0], hi = filter[j][1];\n"
        "                    inverse_input[f*fft_length+j][0] = xr * hr - xi * hi;\n"
        "                    inverse_input[f*fft_length+j][1] = xr * hi + xi * hr;\n"
        "                }\n"
        "            }\n"
        "            fftwf_execute(inverse);\n"
        "            inverse_calls += nf;\n"
        "            for (int f = 0; f < nf; ++f) {\n"
        "                const fftwf_complex *lane = output + f*fft_length;\n"
        "                double *row = k->scores + (size_t)f * ne;",
    )
    source = replace(
        source,
        "const double xr = output[j][0] / fft_length, xi = output[j][1] / fft_length;",
        "const float xr = lane[j][0] / fft_length, xi = lane[j][1] / fft_length;",
    )
    source = replace(
        source, "sqrt(xr * xr + xi * xi) * norm[t]", "(double)sqrtf(xr * xr + xi * xi) * norm[t]"
    )
    source = replace(
        source,
        "(filter_cells + 3 * fft_length) * sizeof(fftwf_complex)",
        "(filter_cells + (2 + 2*(size_t)nf) * fft_length) * sizeof(fftwf_complex)",
    )
    return replace(
        source, "    fftwf_free(output);", "    fftwf_free(inverse_input);\n    fftwf_free(output);"
    )


def build(work):
    original = capture_fft.SOURCE
    base = work / original.name
    base.write_bytes(original.read_bytes())
    bank = work / "folded_bank.c"
    bank.write_text(fft_bank(original.with_name(bank.name).read_text()))
    binary = work / "capture_batched_fft.so"
    cmd = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        str(base),
        "-lfftw3f",
        "-lm",
        "-o",
        str(binary),
    ]
    subprocess.run(cmd, timeout=30, check=True)
    return binary, cmd
