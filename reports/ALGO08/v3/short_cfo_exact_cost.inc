/* Keep the frozen verifier layout. Only populate the ranges this call consumes. */
static int load_frame_support(PortableVerifier *w, const int16_t *iq, unsigned lane,
                              const int32_t *starts, int frames, double offset, int integer) {
    int lo[max_frames], hi[max_frames];
    for (int f = 0; f < frames; ++f) {
        if (integer) {
            lo[f] = starts[f] + first + (int)nearbyint(offset);
            hi[f] = lo[f] + aperture - 1;
        } else {
            lo[f] = (int)(starts[f] + first + offset) - 7;
            hi[f] = (int)(starts[f] + stop - 1 + offset) + 8;
        }
        /* This preserves the original loader on any unexpected geometry. */
        if (lo[f] < 0 || hi[f] >= samples)
            return portable_verifier_load(w, iq, lane);
    }
    for (int f = 0; f < frames; ++f) {
        for (int sample = lo[f]; sample <= hi[f]; ++sample) {
            size_t index = 4 * (size_t)sample + 2 * lane;
            w->iq.fine[sample] = (PortableFineSample){iq[index], iq[index + 1]};
        }
    }
    return 0;
}

/* Preserve the multiply/divide rounding and the original scalar sincos. */
__attribute__((target("avx2"), noinline))
static void prepare_angles(double angles[aperture], int origin, double offset, double cfo) {
#pragma omp simd
    for (int k = 0; k < aperture; ++k) {
        const double position = origin + first + k + offset;
        angles[k] = -tau * cfo * position / rate;
    }
}
