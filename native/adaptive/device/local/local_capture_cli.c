#include "local_source.h"

#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_BLOCKS 100U

struct block_summary {
    uint64_t first, end, missing, sequence;
    uint32_t valid_offset, valid_samples;
};

static int unsigned_value(const char *text, uint64_t maximum, uint64_t *value)
{
    char *end = NULL;
    unsigned long long parsed;

    errno = 0;
    parsed = strtoull(text, &end, 10);
    if (errno || end == text || *end || !parsed || parsed > maximum)
        return -EINVAL;
    *value = (uint64_t)parsed;
    return 0;
}

int main(int argc, char **argv)
{
    struct block_summary summaries[MAX_BLOCKS];
    struct leo_local_restore_receipt restored = { 0 };
    struct leo_local_prime_receipt prime;
    struct leo_local_transition transition;
    struct leo_local_config config = { 0 };
    struct leo_local_source *source = NULL;
    uint64_t frequency, blocks, crc = 0, receivers = 1;
    unsigned completed = 0;
    int ret, close_ret;

    if (argc < 3 || argc > 5 ||
        unsigned_value(argv[1], UINT64_MAX, &frequency) ||
        unsigned_value(argv[2], MAX_BLOCKS, &blocks) ||
        (argc >= 4 && unsigned_value(argv[3], UINT32_MAX, &crc)) ||
        (argc == 5 && unsigned_value(argv[4], 2, &receivers))) {
        fprintf(stderr,
            "usage: %s FREQUENCY_HZ BLOCKS_1_TO_100 [PROFILE_CRC32] [RECEIVERS_1_OR_2]\n",
            argv[0]);
        return 2;
    }
    config.sample_rate_hz = 2500000U;
    config.analog_bandwidth_hz = 2500000U;
    config.samples_per_block = 300000U;
    config.receiver_count = (uint32_t)receivers;
    config.kernel_buffer_count = 4U;
    config.profile_count = 1U;
    config.profiles[0] = (struct leo_local_profile) {
        .profile = 0,
        .frequency_hz = frequency,
        .crc32 = (uint32_t)crc,
    };
    ret = leo_local_source_open(&config, leo_local_iio_provider(), &source);
    if (ret)
        goto fail;
    ret = leo_local_source_prime(source, &prime);
    if (ret)
        goto close;
    ret = leo_local_source_recall(source, 0, &transition);
    if (ret)
        goto close;
    while (completed < blocks) {
        struct leo_local_block block;
        struct leo_local_slice slice;

        ret = leo_local_source_next(source, &block);
        if (ret)
            goto close;
        summaries[completed] = (struct block_summary) {
            .first = block.first_counter,
            .end = block.end_counter,
            .missing = block.missing_samples_before,
            .sequence = block.buffer_sequence,
        };
        ret = leo_local_block_clip(&block, transition.valid_start, UINT64_MAX,
            &slice);
        if (!ret) {
            summaries[completed].valid_offset = slice.sample_offset;
            summaries[completed].valid_samples = slice.samples_per_receiver;
        } else if (ret != -ENODATA) {
            (void)leo_local_source_release(source, &block);
            goto close;
        }
        ret = leo_local_source_release(source, &block);
        if (ret)
            goto close;
        ++completed;
    }

close:
    close_ret = leo_local_source_close(source, &restored);
    source = NULL;
    if (!ret)
        ret = close_ret;
    if (ret)
        goto fail;
    printf("{\"transport\":\"local_iio\",\"sample_rate_hz\":%u,"
        "\"receivers\":%u,\"prime\":{\"first\":%" PRIu64
        ",\"end\":%" PRIu64 ",\"snapshot\":%" PRIu64 "},"
        "\"transition\":{\"before\":%" PRIu64 ",\"after\":%" PRIu64
        ",\"frequency_hz\":%" PRIu64 "},\"blocks\":[",
        config.sample_rate_hz, config.receiver_count,
        prime.discarded_first_counter, prime.discarded_end_counter,
        prime.coherent_counter, transition.previous_valid_end,
        transition.valid_start, transition.frequency_hz);
    for (unsigned i = 0; i < completed; ++i) {
        const struct block_summary *summary = &summaries[i];

        printf("%s{\"first\":%" PRIu64 ",\"end\":%" PRIu64
            ",\"missing\":%" PRIu64 ",\"sequence\":%" PRIu64
            ",\"valid_offset\":%u,\"valid_samples\":%u}",
            i ? "," : "", summary->first, summary->end, summary->missing,
            summary->sequence, summary->valid_offset, summary->valid_samples);
    }
    printf("],\"restore\":{\"frequency_hz\":%" PRIu64
        ",\"before\":%" PRIu64 ",\"after\":%" PRIu64 "}}\n",
        restored.frequency_hz, restored.counter_before, restored.counter_after);
    return 0;

fail:
    if (source)
        (void)leo_local_source_close(source, &restored);
    fprintf(stderr, "local capture failed: %s (%d)\n", strerror(-ret), ret);
    return 3;
}
