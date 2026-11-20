/* Fold one local tile of reconstructed complex FIR outputs. */
#include <math.h>
#include <stddef.h>
#include <stdint.h>

void coarse_basis_fold(const float *dots, const float *normalization,
    int tile, int first, int valid, const int32_t *anchors, int anchor_count,
    int lanes, const int32_t *frames, int frame_count, int epochs, double *scores)
{
    const int last = first + tile;
    for (int anchor = 0; anchor < anchor_count; ++anchor) {
        for (int frame = 0; frame < frame_count; ++frame) {
            const int base = anchors[anchor] + frames[frame];
            const int lo = first > base ? first : base;
            const int remaining = valid < base + epochs ? valid : base + epochs;
            const int hi = last < remaining ? last : remaining;
            if (lo >= hi) continue;
            for (int lane = 0; lane < lanes; ++lane) {
                const float *row = dots + 2 * (size_t)(anchor * lanes + lane) * tile;
                double *score = scores + (size_t)lane * epochs;
                #pragma omp simd
                for (int t = lo; t < hi; ++t) {
                    const float real = row[2 * (t - first)], imag = row[2 * (t - first) + 1];
                    score[t - base] += sqrtf(real * real + imag * imag) * normalization[t];
                }
            }
        }
    }
}
