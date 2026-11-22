void correlated_stencil(const GlrtSample *, const int32_t *, int, const GlrtComplex *,
                        const GlrtComplex *, GlrtComplex [4][max_frames * 64]);

/* Return the number of stencil entries computed by the neighboring-epoch kernel. */
static int packed_integer_stencil(PortableVerifier *w, unsigned epoch, double cfo,
                                  double *scores, unsigned *flags)
{
    if (epoch < 2 || epoch >= n - 2) return 0;
    if (!__builtin_cpu_supports("avx2") || !__builtin_cpu_supports("fma")) return 0;
    int32_t starts[max_frames];
    int frames = 0;
    for (int f = 0; f < max_frames; ++f) {
        int start = frame_start(epoch - 2, f) + first;
        if (start + aperture > samples) break;
        /* Use the original path if one end of the stencil fits an extra frame. */
        if (start + aperture + 4 > samples) return 0;
        starts[frames++] = start;
    }
    prepare_integer_rotation(w, cfo);
    GlrtComplex correlations[4][max_frames * 64];
    correlated_stencil(w->iq.glrt, starts, frames, w->glrt_rotation, w->glrt_exact, correlations);
    for (int k = 0; k < 4; ++k) {
        int best;
        scores[k] = glrt_spectrum(w, correlations[k], frames, &best, flags);
    }
    return 4;
}
