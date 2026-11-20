"""Share one prepared template spectrum across the commensurate CFO grid."""

import subprocess

from . import capture_batched_fft, capture_fft, original_kernel
from .wide_regional import replace


def _shared_cache(header):
    header = replace(
        header, "int taps[22], anchors, lanes;", "int taps[22], shift[21], anchors, lanes;"
    )
    header = replace(
        header,
        "    target->filters=fftwf_alloc_complex((size_t)ns*batch);",
        "    target->filters=fftwf_alloc_complex((size_t)ns*2*fft_length);",
    )
    start = header.index("    double sine[21][maximum_taps]")
    stop = header.index("    for(int s=0;s<ns;++s)", start)
    header = (
        header[:start]
        + """    const double center=k->frequencies[nf/2];
    double sine[maximum_taps], cosine[maximum_taps];
    for(int f=0;f<nf;++f) {
        const double shift=(k->frequencies[f]-center)*fft_length/k->sample_rate_hz;
        if(fabs(shift)>fft_length || fabs(shift-round(shift))>1e-12) goto error;
        const int bin=(int)round(shift);
        target->shift[f]=(fft_length-bin)%fft_length;
    }
    for(int j=0;j<maximum_taps;++j) {
        const double angle=6.283185307179586476925286766559*center*j/k->sample_rate_hz;
        sine[j]=sin(angle);
        cosine[j]=cos(angle);
    }
"""
        + header[stop:]
    )
    anchor_loop = header.index("    for(int s=0;s<ns;++s) {")
    start = header.index("        for(int f=0;f<nf;++f) {", anchor_loop)
    stop = header.index("    target->used=++cache_clock;", start)
    header = (
        header[:start]
        + """        memset(target->input,0,fft_length*sizeof(fftwf_complex));
        for(int t=0;t<taps[s];++t) {
            const double real=creal(target->refs[s][t]), imag=cimag(target->refs[s][t]);
            const int j=taps[s]-1-t;
            target->input[j][0]=(float)(real*cosine[t]-imag*sine[t]);
            target->input[j][1]=(float)-(real*sine[t]+imag*cosine[t]);
        }
        fftwf_execute(target->forward);
        fftwf_complex *base=target->filters+(size_t)s*2*fft_length;
        memcpy(base,target->spectrum,fft_length*sizeof(fftwf_complex));
        memcpy(base+fft_length,target->spectrum,fft_length*sizeof(fftwf_complex));
    }
"""
        + header[stop:]
    )
    return replace(header, "*built=ns*nf;", "*built=ns;")


def build(work, length):
    """Build a prepared control with FFTW-ready circular shifts of the filter spectra."""
    if length not in (250, 500, 1000):
        raise ValueError("80 kHz lanes at 10 Msps require a supported multiple of 125")
    work.mkdir()
    path = work / capture_fft.SOURCE.name
    path.write_bytes(capture_fft.SOURCE.read_bytes())
    canonical = capture_fft.SOURCE.with_name("folded_bank.c")
    source = original_kernel.kernel(capture_batched_fft.fft_bank(canonical.read_text()))
    source = replace(source, "fft_length = 512", f"fft_length = {length}")
    source = replace(source, "original_kernel_cache.h", "coarse_basis_shift.h")
    source = replace(
        source, "filter_cells=(size_t)ns*nf*fft_length", "filter_cells=(size_t)ns*2*fft_length"
    )
    source = replace(
        source,
        "filters + ((size_t)s * nf + f) * fft_length",
        "filters + (size_t)s * 2 * fft_length + ready->shift[f]",
    )
    (work / canonical.name).write_text(source)
    (work / "coarse_basis_shift.h").write_text(_shared_cache(original_kernel.HEADER.read_text()))
    library = work / "coarse_basis_shift.so"
    command = [
        "cc",
        *capture_fft.FLAGS,
        "-march=native",
        "-fopenmp-simd",
        "-fno-math-errno",
        "-fno-trapping-math",
        str(path),
        "-lfftw3f",
        "-lm",
        "-o",
        str(library),
    ]
    subprocess.run(command, check=True, timeout=30)
    return library, command
