#include <stdint.h>
#include <string.h>

/* Starts and exclusive ends of unchanged runs on the physical lane. */
int equal_iq_runs(const int16_t *raw, const int16_t *residual, int samples, int lane,
                  int32_t *runs) {
    int start = -1, used = 0;
    for (int n = 0; n < samples; ++n) {
        int offset = 4 * n + 2 * lane;
        int equal = !((raw[offset] ^ residual[offset]) | (raw[offset + 1] ^ residual[offset + 1]));
        if (equal && start < 0) start = n;
        if (!equal && start >= 0) {
            runs[2 * used] = start;
            runs[2 * used + 1] = n;
            ++used;
            start = -1;
        }
    }
    if (start >= 0) {
        runs[2 * used] = start;
        runs[2 * used + 1] = samples;
        ++used;
    }
    return used;
}

void copy_retained_input(void *destination, const void *source, size_t bytes) {
    memcpy(destination, source, bytes);
}
