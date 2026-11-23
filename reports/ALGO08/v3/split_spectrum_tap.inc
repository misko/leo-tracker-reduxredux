typedef struct {
    unsigned seen, flags, frames, templates;
    double power[2][2][glrt_size];
} SplitSpectrum;

static _Thread_local SplitSpectrum split_trace;
static _Thread_local int split_fractional;

void split_spectrum_reset(void) {
    split_fractional = 0;
    split_trace.seen = split_trace.flags = split_trace.frames = split_trace.templates = 0;
}

const SplitSpectrum *split_spectrum_trace(void) { return &split_trace; }

static void split_finish(PortableVerifier *w, int frames,
                         const double halves[2][short_size], const double ceiling[2]) {
    if (split_trace.templates >= 2) return;
    split_trace.frames = (unsigned)frames;
    double (*out)[glrt_size] = split_trace.power[split_trace.templates++];
    for (int h = 0; h < 2; ++h) {
        if (ceiling[h] == 0) {
            memset(out[h], 0, sizeof(out[h]));
            continue;
        }
        for (int k = 0; k < short_size; ++k) w->fft_input[k] = halves[h][k];
        leo_fft_forward(&w->fft128, w->fft_input);
        memset(w->fft_input, 0, sizeof(w->fft_input));
        for (int k = 0; k < 64; ++k)
            w->fft_input[k] = conj(w->fft128.output[k])/short_size;
        for (int k = 1; k < 64; ++k)
            w->fft_input[glrt_size-k] = conj(w->fft128.output[short_size-k])/short_size;
        leo_fft_forward(&w->fft512, w->fft_input);
        for (int k = 0; k < glrt_size; ++k)
            out[h][k] = creal(w->fft512.output[k])/ceiling[h];
    }
}
