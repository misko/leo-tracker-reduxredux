#ifndef LEO_ARM_CENTER_PAIR_H
#define LEO_ARM_CENTER_PAIR_H

/* Score two adjacent early integer starts without changing either reduction. */
static int leo_center_pair(leo_presence_workspace *w, size_t count, int epoch,
    double cfo, double score[2][3], unsigned *used_frames)
{
    *used_frames = 0;
#if LEO_PRESENCE_PRECOMPUTE && LEO_PRESENCE_EPOCH_FRAMES == 16 && \
    !LEO_PRESENCE_ENERGY_SYMBOL_SUPPORT && !LEO_PRESENCE_GLRT_SYMBOL_DIVERSITY
    if (!w->wide_regional || count != 200000 || w->rate != 10000000 || w->n != 13333 ||
        w->acquisition_first_frame != 0 || epoch < 0 || epoch + 1 >= (int)w->n ||
        !isfinite(cfo) || fabs(cfo) > regional_cfo_limit(w)) return 0;
    const int first = symbol_start(w, 2), stop = symbol_start(w, 66);
    int starts[16];
    unsigned used = 0;
    for (int frame = 0; frame < 16; ++frame) {
        const int a = frame_start(w, epoch, frame);
        const int b = frame_start(w, epoch + 1, frame);
        if (a + stop - 1 >= (int)count) break;
        if (a + first < 0 || b != a + 1 || b + stop - 1 >= (int)count) return 0;
        starts[used++] = a;
    }
    *used_frames = used;
    glrt_prepare_rotations(w, cfo, 0, 0);
    double spectra[2][2][128] = {{{0}}}, ceilings[2][2] = {{0}};
    for (unsigned frame = 0; frame < used; ++frame) {
        const double complex *received = w->samples + starts[frame];
        double complex a[2][64] = {{0}}, b[2][64] = {{0}};
        for (int s = 0; s < 64; ++s) {
            const int begin = symbol_start(w, s + 2), end = symbol_start(w, s + 3);
            for (int k = begin; k < end; ++k) {
                const double complex x = received[k], y = received[k + 1];
                const double complex exact = w->glrt_exact_rotated[k];
                const double complex rolled = w->glrt_control_rotated[k];
                a[0][s] += x * exact;
                a[1][s] += x * rolled;
                b[0][s] += y * exact;
                b[1][s] += y * rolled;
            }
        }
        glrt_add_frame(w, a, spectra[0], ceilings[0]);
        glrt_add_frame(w, b, spectra[1], ceilings[1]);
    }
    glrt_finish(w, spectra[0], ceilings[0], score[0]);
    glrt_finish(w, spectra[1], ceilings[1], score[1]);
    return 1;
#else
    (void)w; (void)count; (void)epoch; (void)cfo; (void)score;
    return 0;
#endif
}

#endif
