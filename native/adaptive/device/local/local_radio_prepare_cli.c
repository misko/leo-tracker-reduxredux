#include "local_radio_prepare.h"
#include "local_source.h"

#include <errno.h>
#include <inttypes.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static int number(const char *text, uint64_t maximum, int allow_zero, uint64_t *out)
{
    char *end;
    unsigned long long value;
    if (!text || *text == '-') return -EINVAL;
    errno = 0;
    value = strtoull(text, &end, 10);
    if (errno || end == text || *end || (!allow_zero && !value) || value > maximum)
        return -EINVAL;
    *out = value;
    return 0;
}

static int monotonic_ns(uint64_t *out)
{
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now)) return -errno;
    *out = (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
    return 0;
}

static void print_settings(const char *name, const leo_local_radio_settings *value)
{
    printf(",\"%s\":{\"frequency_hz\":%" PRIu64
        ",\"source_rate_hz\":%u,\"capture_rate_hz\":%u,"
        "\"bandwidth_hz\":%u,\"receiver_mask\":%u,"
        "\"gain_modes\":[\"%s\",\"%s\"],\"gain_millidb\":[%d,%d]}",
        name, value->center_frequency_hz, value->sample_rate_hz,
        value->capture_sample_rate_hz, value->analog_bandwidth_hz,
        value->receiver_mask, value->gain_mode[0], value->gain_mode[1],
        value->gain_millidb[0], value->gain_millidb[1]);
}

int main(int argc, char **argv)
{
    leo_local_radio_prepare_config prepare = { 0 };
    leo_local_radio_prepare_receipt prepared = { 0 };
    leo_local_radio_restore_receipt restored = { 0 };
    leo_local_restore_receipt owner_receipt = { 0 };
    leo_local_config local = { 0 };
    leo_local_radio_preparation *handle = NULL;
    leo_local_owner *owner = NULL;
    uint64_t duration, started, now;
    uint32_t i;
    int owner_status = 0, restore_status = 0, ret;

    if (argc < 7 || strcmp(argv[1], "--prepare-only") ||
        strcmp(argv[2], "--duration-ms") ||
        number(argv[3], UINT64_C(1800000), 0, &duration))
        goto usage;
    prepare.abi_version = LEO_LOCAL_RADIO_PREPARE_ABI_VERSION;
    prepare.sample_rate_hz = 2500000U;
    prepare.analog_bandwidth_hz = 2500000U;
    prepare.receiver_count = 2U;
    prepare.manual_gain_millidb = 40000;
    for (i = 4U; i < (uint32_t)argc;) {
        uint64_t profile, frequency;
        if (strcmp(argv[i++], "--target") || i + 1U >= (uint32_t)argc ||
            prepare.target_count == LEO_LOCAL_RADIO_MAX_TARGETS ||
            number(argv[i++], 7U, 1, &profile) ||
            number(argv[i++], UINT64_C(6000000000), 0, &frequency) ||
            frequency < UINT64_C(70000000))
            goto usage;
        prepare.targets[prepare.target_count].profile = (uint32_t)profile;
        prepare.targets[prepare.target_count].frequency_hz = frequency;
        ++prepare.target_count;
    }
    if (!prepare.target_count) goto usage;
    ret = monotonic_ns(&started);
    if (ret) return 3;
    local.sample_rate_hz = prepare.sample_rate_hz;
    local.analog_bandwidth_hz = prepare.analog_bandwidth_hz;
    local.samples_per_block = 300000U;
    local.receiver_count = prepare.receiver_count;
    local.kernel_buffer_count = LEO_LOCAL_RADIO_KERNEL_BUFFERS;
    local.profile_count = prepare.target_count;
    for (i = 0U; i < prepare.target_count; ++i) {
        local.profiles[i].profile = prepare.targets[i].profile;
        local.profiles[i].frequency_hz = prepare.targets[i].frequency_hz;
    }
    ret = leo_local_radio_preflight_inactive(
        leo_local_iio_radio_prepare_provider());
    if (!ret) ret = leo_local_owner_acquire(&local, leo_local_iio_provider(), &owner);
    if (!ret) ret = leo_local_radio_prepare_owned(&prepare,
        leo_local_iio_radio_prepare_provider(), owner, &handle, &prepared);
    if (!monotonic_ns(&now) && now - started >= duration * UINT64_C(1000000) && !ret)
        ret = -ETIMEDOUT;
    if (handle) {
        restore_status = leo_local_radio_restore(&handle, owner, &restored);
        if (restore_status && handle)
            restore_status = leo_local_radio_restore(&handle, owner, &restored);
    }
    if (!monotonic_ns(&now) && now - started >= duration * UINT64_C(1000000) && !ret)
        ret = -ETIMEDOUT;
    if (owner)
        owner_status = leo_local_owner_release(owner, 0U, &owner_receipt);
    printf("{\"schema\":\"leo-local-radio-prepare/v1\",\"prepare_status\":%d,"
        "\"restore_status\":%d,\"owner_status\":%d,\"targets\":[",
        ret, restore_status, owner_status);
    for (i = 0U; i < prepared.target_count; ++i) {
        if (i) putchar(',');
        printf("{\"profile\":%u,\"frequency_hz\":%" PRIu64
            ",\"profile_crc32\":%u}", prepared.targets[i].profile,
            prepared.targets[i].frequency_hz, prepared.targets[i].profile_crc32);
    }
    putchar(']');
    print_settings("original", &prepared.original);
    print_settings("configured", &prepared.configured);
    print_settings("restored", &restored.observed);
    print_settings("failure_cleanup_observed", &prepared.cleanup_observed);
    printf(",\"original_kernel_buffers\":%u,\"configured_kernel_buffers\":%u,"
        "\"restored_kernel_buffers\":%u,\"fastlock_inactive\":%s,"
        "\"failure_cleanup_attempted\":%s,\"failure_cleanup_status\":%d,"
        "\"failure_cleanup_kernel_buffers\":%u,"
        "\"failure_cleanup_fastlock_inactive\":%s}\n",
        prepared.original_kernel_buffers, prepared.configured_kernel_buffers,
        restored.observed_kernel_buffers,
        restored.fastlock_inactive ? "true" : "false",
        prepared.cleanup_attempted ? "true" : "false",
        prepared.cleanup_status, prepared.cleanup_observed_kernel_buffers,
        prepared.cleanup_fastlock_inactive ? "true" : "false");
    return ret || restore_status || owner_status || handle ? 4 : 0;

usage:
    fprintf(stderr, "usage: %s --prepare-only --duration-ms 1..1800000 "
        "--target PROFILE FREQUENCY_HZ [--target ...]\n", argv[0]);
    return 2;
}
