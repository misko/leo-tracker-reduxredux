#define _GNU_SOURCE
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* Compile the production-private fold implementation into this component test.
 * The normal detector build compiles the same file through
 * kernel/proposal_core_wrapper.c. */
#define LEO_PROPOSAL_LIBRARY 1
#include "../../../native/adaptive/detector/kernel/private/proposal_core.c"

enum { SAMPLE_COUNT = 96, OUTPUT_COUNT = 16 };

static uint32_t float_bits(float value)
{
    uint32_t bits;
    memcpy(&bits, &value, sizeof(bits));
    return bits;
}

static void fill_input(int16_t dual[SAMPLE_COUNT * 4], int pattern)
{
    static const int16_t extremes[] = {
        INT16_MIN, INT16_MAX, -32767, 32766, -1, 0, 1, 17, -31
    };
    uint32_t state = 0x6d2b79f5u;
    for (size_t sample = 0; sample < SAMPLE_COUNT; ++sample) {
        for (size_t scalar = 0; scalar < 4; ++scalar) {
            if (!pattern) {
                const size_t index = sample * 7u + scalar * 5u + sample / 3u;
                dual[4u * sample + scalar] =
                    extremes[index % (sizeof(extremes) / sizeof(extremes[0]))];
            } else {
                state = state * 1664525u + 1013904223u;
                dual[4u * sample + scalar] = (int16_t)(state >> 16);
            }
        }
    }
}

static void extract_receiver(const int16_t dual[SAMPLE_COUNT * 4], int receiver,
                             int16_t single[SAMPLE_COUNT * 2])
{
    for (size_t sample = 0; sample < SAMPLE_COUNT; ++sample) {
        single[2u * sample] = dual[4u * sample + 2u * (size_t)receiver];
        single[2u * sample + 1u] =
            dual[4u * sample + 2u * (size_t)receiver + 1u];
    }
}

static void initialize_output(fftwf_complex output[3][OUTPUT_COUNT])
{
    for (size_t method = 0; method < 3; ++method) {
        for (size_t sample = 0; sample < OUTPUT_COUNT; ++sample) {
            output[method][sample][0] =
                (float)(method * OUTPUT_COUNT + sample + 1u) * 0.25f;
            output[method][sample][1] =
                -(float)(method * OUTPUT_COUNT + sample + 1u) * 0.125f;
        }
    }
}

static int compare_output(const fftwf_complex dual[3][OUTPUT_COUNT],
                          const fftwf_complex single[3][OUTPUT_COUNT],
                          const size_t valid[3], int pattern, int receiver,
                          size_t start, size_t off, const char *implementation)
{
    for (size_t method = 0; method < 3; ++method) {
        for (size_t sample = 0; sample < OUTPUT_COUNT; ++sample) {
            for (size_t component = 0; component < 2; ++component) {
                const uint32_t left = float_bits(dual[method][sample][component]);
                const uint32_t right = float_bits(single[method][sample][component]);
                if (left != right) {
                    fprintf(stderr,
                        "fold mismatch implementation=%s pattern=%d receiver=%d "
                        "start=%zu off=%zu "
                        "valid=%zu/%zu/%zu method=%zu sample=%zu component=%zu "
                        "dual=%08x single=%08x\n",
                        implementation, pattern, receiver, start, off, valid[0],
                        valid[1], valid[2], method, sample, component, left,
                        right);
                    return -1;
                }
            }
        }
    }
    return 0;
}

static int run_case(const int16_t dual[SAMPLE_COUNT * 4], int receiver,
                    int pattern, size_t start, size_t off,
                    const size_t valid[3], int use_neon)
{
    int16_t single[SAMPLE_COUNT * 2];
    int16_t dual_before[SAMPLE_COUNT * 4];
    int16_t single_before[SAMPLE_COUNT * 2];
    fftwf_complex dual_output[3][OUTPUT_COUNT];
    fftwf_complex single_output[3][OUTPUT_COUNT];
    fftwf_complex *dual_lanes[3] = {
        dual_output[0], dual_output[1], dual_output[2]
    };
    fftwf_complex *single_lanes[3] = {
        single_output[0], single_output[1], single_output[2]
    };
    size_t mutable_valid[3] = {valid[0], valid[1], valid[2]};

    extract_receiver(dual, receiver, single);
    memcpy(dual_before, dual, sizeof(dual_before));
    memcpy(single_before, single, sizeof(single_before));
    initialize_output(dual_output);
    initialize_output(single_output);

#ifdef LEO_PROPOSAL_NEON_FOLD
    if (use_neon) {
        fold_three_neon(dual_lanes, dual, start, off, mutable_valid, receiver);
        fold_three_single_neon(single_lanes, single, start, off, mutable_valid);
    } else
#else
    (void)use_neon;
#endif
    {
    fold_three_scalar(dual_lanes, dual, start, off, mutable_valid, receiver);
    fold_three_single_scalar(single_lanes, single, start, off, mutable_valid);
    }

    if (memcmp(dual, dual_before, sizeof(dual_before)) ||
        memcmp(single, single_before, sizeof(single_before))) {
        fprintf(stderr, "fold mutated input\n");
        return -1;
    }
    return compare_output(dual_output, single_output, valid, pattern, receiver,
                          start, off, use_neon ? "neon" : "scalar");
}

int main(void)
{
    static const size_t positions[][2] = {{0u, 0u}, {3u, 2u}};
    int16_t dual[SAMPLE_COUNT * 4];

    for (int pattern = 0; pattern < 2; ++pattern) {
        fill_input(dual, pattern);
        for (int receiver = 0; receiver < 2; ++receiver) {
            for (size_t position = 0;
                 position < sizeof(positions) / sizeof(positions[0]);
                 ++position) {
                for (size_t lag1 = 0; lag1 <= 9; ++lag1) {
                    for (size_t lag3 = 0; lag3 <= 9; ++lag3) {
                        for (size_t lag5 = 0; lag5 <= 9; ++lag5) {
                            const size_t valid[3] = {lag1, lag3, lag5};
                            if (run_case(dual, receiver, pattern,
                                         positions[position][0],
                                         positions[position][1], valid, 0))
                                return 1;
#ifdef LEO_PROPOSAL_NEON_FOLD
                            if (run_case(dual, receiver, pattern,
                                         positions[position][0],
                                         positions[position][1], valid, 1))
                                return 1;
#endif
                        }
                    }
                }
            }
        }
    }
    return 0;
}
