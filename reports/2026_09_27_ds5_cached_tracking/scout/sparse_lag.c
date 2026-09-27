#define _POSIX_C_SOURCE 200809L
#include <math.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
#include <time.h>

typedef struct {
    double window_scores[6];
    double power_sum_score;
    uint32_t pairs_per_window;
    double cpu_ms;
    double wall_ms;
} scout_sparse_result;

static double now(clockid_t id)
{
    struct timespec value;
    if (clock_gettime(id, &value)) return 0;
    return value.tv_sec * 1000.0 + value.tv_nsec / 1e6;
}

int scout_sparse_lag3_ci16(const int16_t *iq, size_t count, uint32_t rate,
    uint32_t stride, scout_sparse_result *out)
{
    if (!iq || !out || (rate != 2500000 && rate != 5000000) ||
        count != (size_t)rate * 120 / 1000 ||
        stride != (rate == 2500000 ? 8u : 16u)) return -1;
    scout_sparse_result result;
    memset(&result, 0, sizeof(result));
    const size_t window = rate / 50, lag = rate / 250;
    double normalized_power_sum = 0;
    const double cpu = now(CLOCK_THREAD_CPUTIME_ID), wall = now(CLOCK_MONOTONIC);
    for (size_t w = 0; w < 6; ++w) {
        int64_t cross_real = 0, cross_imag = 0;
        uint64_t first_energy = 0, second_energy = 0;
        uint32_t pairs = 0;
        const size_t base = w * window;
        for (size_t k = 0; k + lag < window; k += stride) {
            const int64_t ar = iq[2 * (base + k)], ai = iq[2 * (base + k) + 1];
            const int64_t br = iq[2 * (base + k + lag)];
            const int64_t bi = iq[2 * (base + k + lag) + 1];
            cross_real += ar * br + ai * bi;
            cross_imag += ai * br - ar * bi;
            first_energy += (uint64_t)(ar * ar + ai * ai);
            second_energy += (uint64_t)(br * br + bi * bi);
            ++pairs;
        }
        const double cross_power = (double)cross_real * cross_real +
            (double)cross_imag * cross_imag;
        const double energy_product = (double)first_energy * second_energy;
        result.window_scores[w] = energy_product > 0 ? sqrt(cross_power / energy_product) : 0;
        normalized_power_sum += result.window_scores[w] * result.window_scores[w];
        result.pairs_per_window = pairs;
    }
    result.power_sum_score = sqrt(normalized_power_sum / 6.0);
    result.cpu_ms = now(CLOCK_THREAD_CPUTIME_ID) - cpu;
    result.wall_ms = now(CLOCK_MONOTONIC) - wall;
    *out = result;
    return 0;
}
