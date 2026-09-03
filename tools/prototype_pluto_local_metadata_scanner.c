// SPDX-License-Identifier: GPL-2.0-or-later
/*
 * Bounded, fail-closed proof of the scanner timing ceiling when the capture
 * loop runs beside the Pluto IIO provider. This is a development prototype,
 * not a production acquisition service: IQ is acquired and sparsely touched
 * on-radio, but is not transported or persisted.
 */

#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <iio.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define ARRAY_SIZE(value) (sizeof(value) / sizeof((value)[0]))
#define FRAMES_PER_RATE 32U
#define DWELL_MS 120U
#define SETTLE_US 250U
#define METADATA_CAPACITY (64U * 1024U)
#define EXPECTED_SERIAL "1040007c4a94000211000b009186843ef2"
#define METADATA_MAGIC 0x314d4753U
#define METADATA_VERSION 6U
#define FLAG_SAMPLE_SEQUENCE_VALID (1U << 4)
#define FLAG_DEVICE_IIO_OVERFLOW (1U << 11)
#define FLAG_FPGA_EVENT_OVERFLOW (1U << 13)
#define FLAG_GAIN_OBSERVATION_OVERFLOW (1U << 20)
#define FLAG_HARDWARE_SAMPLE_COUNTER_VALID (1U << 21)
#define FLAG_TANDEM_METADATA_VALID (1U << 22)
#define FLAG_SAMPLE_GAP_BEFORE (1U << 23)

static const long long frequencies_hz[] = {
    959687500LL,
    1209687500LL,
    1459687500LL,
    1709687500LL,
    1190312500LL,
    1440312500LL,
    1690312500LL,
    1940312500LL,
};

/* TandemSessionRequestV1(mode=HOLD), frozen ABI-3 wire representation. */
static const uint8_t tandem_hold_request[] = {
    0x53, 0x50, 0x46, 0x54, 0x01, 0x00, 0x68, 0x00,
    0x07, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x40, 0x00, 0x00, 0x00, 0x40, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x3e, 0x00, 0x00, 0x00,
    0x1e, 0x00, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00,
    0x03, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00,
    0x04, 0x00, 0x00, 0x00, 0x04, 0x00, 0x00, 0x00,
    0x08, 0x00, 0x00, 0x00, 0x14, 0x3a, 0x31, 0x30,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
};

_Static_assert(sizeof(tandem_hold_request) == 104U,
    "ABI-3 tandem HOLD request must remain 104 bytes");

struct timings {
    double values[FRAMES_PER_RATE];
};

struct preserved_settings {
    char lo[128];
    char rate[128];
    char bandwidth[128];
    char gain_mode[2][128];
    char gain[2][128];
};

static double now_seconds(void)
{
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC, &value);
    return value.tv_sec + value.tv_nsec / 1e9;
}

static void sleep_microseconds(unsigned int microseconds)
{
    struct timespec delay = {
        .tv_sec = microseconds / 1000000U,
        .tv_nsec = (long)(microseconds % 1000000U) * 1000L,
    };
    while (nanosleep(&delay, &delay) < 0 && errno == EINTR)
        ;
}

static uint16_t read_le16(const uint8_t *value)
{
    return (uint16_t)value[0] | (uint16_t)value[1] << 8;
}

static uint32_t read_le32(const uint8_t *value)
{
    return (uint32_t)value[0] | (uint32_t)value[1] << 8 |
        (uint32_t)value[2] << 16 | (uint32_t)value[3] << 24;
}

static uint64_t read_le64(const uint8_t *value)
{
    return (uint64_t)read_le32(value) | (uint64_t)read_le32(value + 4) << 32;
}

static uint32_t crc32_bytes(const uint8_t *data, size_t bytes)
{
    uint32_t crc = 0xffffffffU;
    size_t index;
    unsigned int bit;

    for (index = 0; index < bytes; ++index) {
        uint8_t byte = index + 4U >= bytes ? 0U : data[index];
        crc ^= byte;
        for (bit = 0; bit < 8; ++bit)
            crc = crc & 1U ? (crc >> 1) ^ 0xedb88320U : crc >> 1;
    }
    return crc ^ 0xffffffffU;
}

static int compare_double(const void *left, const void *right)
{
    const double a = *(const double *)left;
    const double b = *(const double *)right;
    return (a > b) - (a < b);
}

static double quantile(const struct timings *input, double fraction)
{
    double values[FRAMES_PER_RATE];
    double position, weight;
    unsigned int lower, upper;

    memcpy(values, input->values, sizeof(values));
    qsort(values, FRAMES_PER_RATE, sizeof(values[0]), compare_double);
    position = fraction * (FRAMES_PER_RATE - 1U);
    lower = (unsigned int)position;
    upper = lower + 1U < FRAMES_PER_RATE ? lower + 1U : lower;
    weight = position - lower;
    return values[lower] * (1.0 - weight) + values[upper] * weight;
}

static double mean(const struct timings *input)
{
    double sum = 0.0;
    unsigned int index;

    for (index = 0; index < FRAMES_PER_RATE; ++index)
        sum += input->values[index];
    return sum / FRAMES_PER_RATE;
}

static double maximum(const struct timings *input)
{
    double result = input->values[0];
    unsigned int index;

    for (index = 1; index < FRAMES_PER_RATE; ++index)
        if (input->values[index] > result)
            result = input->values[index];
    return result;
}

static void print_stats(const char *name, const struct timings *values, bool comma)
{
    printf("      \"%s\": {\"mean_ms\": %.6f, \"p50_ms\": %.6f, "
           "\"p95_ms\": %.6f, \"max_ms\": %.6f}%s\n",
           name, mean(values) * 1000.0, quantile(values, 0.50) * 1000.0,
           quantile(values, 0.95) * 1000.0, maximum(values) * 1000.0,
           comma ? "," : "");
}

static int preserve_settings(
    struct iio_channel *lo,
    struct iio_channel *rx_phy[2],
    struct preserved_settings *settings)
{
    unsigned int index;

    if (iio_channel_attr_read(lo, "frequency", settings->lo,
            sizeof(settings->lo)) < 0 ||
        iio_channel_attr_read(rx_phy[0], "sampling_frequency", settings->rate,
            sizeof(settings->rate)) < 0 ||
        iio_channel_attr_read(rx_phy[0], "rf_bandwidth", settings->bandwidth,
            sizeof(settings->bandwidth)) < 0)
        return -1;
    for (index = 0; index < 2; ++index) {
        if (iio_channel_attr_read(rx_phy[index], "gain_control_mode",
                settings->gain_mode[index], sizeof(settings->gain_mode[index])) < 0 ||
            iio_channel_attr_read(rx_phy[index], "hardwaregain",
                settings->gain[index], sizeof(settings->gain[index])) < 0)
            return -1;
    }
    return 0;
}

static void restore_settings(
    struct iio_channel *lo,
    struct iio_channel *rx_phy[2],
    const struct preserved_settings *settings)
{
    unsigned int index;

    (void)iio_channel_attr_write(rx_phy[0], "rf_bandwidth", settings->bandwidth);
    (void)iio_channel_attr_write(rx_phy[0], "sampling_frequency", settings->rate);
    (void)iio_channel_attr_write(lo, "frequency", settings->lo);
    for (index = 0; index < 2; ++index) {
        (void)iio_channel_attr_write(rx_phy[index], "gain_control_mode", "manual");
        (void)iio_channel_attr_write(rx_phy[index], "hardwaregain", settings->gain[index]);
        (void)iio_channel_attr_write(rx_phy[index], "gain_control_mode",
            settings->gain_mode[index]);
    }
}

static int prepare_fastlock_profiles(struct iio_channel *lo)
{
    char saved[256];
    unsigned int index;
    ssize_t bytes;

    for (index = 0; index < ARRAY_SIZE(frequencies_hz); ++index) {
        char *end = NULL;
        unsigned long slot;

        if (iio_channel_attr_write_longlong(lo, "frequency",
                frequencies_hz[index]) < 0 ||
            iio_channel_attr_write_longlong(lo, "fastlock_store", index) < 0 ||
            iio_channel_attr_write_longlong(lo, "fastlock_save", index) < 0) {
            fprintf(stderr, "failed to prepare Fast Lock slot %u: %s\n",
                index, strerror(errno));
            return -1;
        }
        bytes = iio_channel_attr_read(lo, "fastlock_save", saved,
            sizeof(saved) - 1U);
        if (bytes <= 0 || (size_t)bytes >= sizeof(saved)) {
            fprintf(stderr, "failed to read Fast Lock slot %u\n", index);
            return -1;
        }
        saved[bytes] = '\0';
        errno = 0;
        slot = strtoul(saved, &end, 10);
        if (errno || end == saved || slot != index || (*end != ' ' && *end != '\t')) {
            fprintf(stderr, "malformed Fast Lock slot %u readback\n", index);
            return -1;
        }
    }
    return 0;
}

static int validate_metadata(
    const uint8_t *metadata,
    size_t metadata_bytes,
    size_t samples,
    uint64_t *stream_ids,
    unsigned int stream_count)
{
    uint16_t header_bytes;
    uint32_t flags, expected_crc, actual_crc;
    uint64_t stream_id;
    unsigned int index;

    if (metadata_bytes < 124U) {
        fprintf(stderr, "short metadata header: %zu bytes\n", metadata_bytes);
        return -1;
    }
    header_bytes = read_le16(metadata + 6);
    if (read_le32(metadata) != METADATA_MAGIC ||
        read_le16(metadata + 4) != METADATA_VERSION ||
        header_bytes != metadata_bytes) {
        fprintf(stderr, "bad metadata identity or length\n");
        return -1;
    }
    expected_crc = read_le32(metadata + metadata_bytes - 4U);
    actual_crc = crc32_bytes(metadata, metadata_bytes);
    if (actual_crc != expected_crc) {
        fprintf(stderr, "metadata CRC mismatch: %08" PRIx32 " != %08" PRIx32 "\n",
            actual_crc, expected_crc);
        return -1;
    }
    flags = read_le32(metadata + 12);
    if ((flags & (FLAG_SAMPLE_SEQUENCE_VALID |
            FLAG_HARDWARE_SAMPLE_COUNTER_VALID |
            FLAG_TANDEM_METADATA_VALID)) !=
            (FLAG_SAMPLE_SEQUENCE_VALID |
             FLAG_HARDWARE_SAMPLE_COUNTER_VALID |
             FLAG_TANDEM_METADATA_VALID) ||
        flags & (FLAG_DEVICE_IIO_OVERFLOW | FLAG_FPGA_EVENT_OVERFLOW |
            FLAG_GAIN_OBSERVATION_OVERFLOW | FLAG_SAMPLE_GAP_BEFORE)) {
        fprintf(stderr, "metadata validity/overflow flags rejected: %08" PRIx32 "\n", flags);
        return -1;
    }
    if (read_le64(metadata + 24) != 0U ||
        read_le32(metadata + 40) != samples ||
        read_le32(metadata + 44) != samples * 8U ||
        read_le32(metadata + 48) != 0x0fU || metadata[54] != 2U ||
        read_le64(metadata + 116) != 0U) {
        fprintf(stderr, "metadata geometry, sequence, or gap check failed\n");
        return -1;
    }
    stream_id = read_le64(metadata + 16);
    if (!stream_id) {
        fprintf(stderr, "zero stream ID\n");
        return -1;
    }
    for (index = 0; index < stream_count; ++index) {
        if (stream_ids[index] == stream_id) {
            fprintf(stderr, "stream ID reused across capture resets\n");
            return -1;
        }
    }
    stream_ids[stream_count] = stream_id;
    return 0;
}

static int run_rate(
    struct iio_device *rx,
    struct iio_channel *lo,
    struct iio_channel *rx_phy[2],
    long long sample_rate,
    bool metadata_mode,
    unsigned int refill_ms,
    uint32_t *checksum)
{
    const size_t dwell_samples = (size_t)(sample_rate * DWELL_MS / 1000LL);
    const size_t buffer_samples = (size_t)(sample_rate * refill_ms / 1000LL);
    const unsigned int refills_per_target = DWELL_MS / refill_ms;
    struct iio_buffer *prime = NULL;
    struct timings tune = {0}, create = {0}, refill = {0};
    struct timings touch = {0}, destroy = {0}, whole = {0};
    uint8_t metadata[METADATA_CAPACITY];
    uint64_t stream_ids[FRAMES_PER_RATE] = {0};
    uint64_t payload_bytes = 0;
    double run_start, before, after, frame_start, wall_seconds;
    unsigned int index;

    if (iio_channel_attr_write_longlong(rx_phy[0], "sampling_frequency",
            sample_rate) < 0 ||
        iio_channel_attr_write_longlong(rx_phy[0], "rf_bandwidth", sample_rate) < 0) {
        fprintf(stderr, "failed to configure rate %lld: %s\n", sample_rate,
            strerror(errno));
        return -1;
    }

    /* Match the production metadata session admission sequence: one ordinary
     * refill establishes and proves the requested dual-RX scan layout. */
    prime = iio_device_create_buffer(rx, buffer_samples, false);
    if (!prime || iio_buffer_refill(prime) != (ssize_t)(buffer_samples * 8U)) {
        fprintf(stderr, "ordinary scan-layout prime failed at %lld Hz: %s\n",
            sample_rate, strerror(errno));
        if (prime)
            iio_buffer_destroy(prime);
        return -1;
    }
    iio_buffer_destroy(prime);

    run_start = now_seconds();
    for (index = 0; index < FRAMES_PER_RATE; ++index) {
        struct iio_buffer *buffer;
        const uint8_t *start, *end;
        size_t metadata_bytes = 0, bytes;
        ssize_t refill_bytes;
        double refill_total = 0.0, touch_total = 0.0;
        unsigned int refill_index;

        frame_start = now_seconds();
        before = now_seconds();
        if ((metadata_mode
                ? iio_channel_attr_write_longlong(lo, "frequency",
                    frequencies_hz[index % ARRAY_SIZE(frequencies_hz)])
                : iio_channel_attr_write_longlong(lo, "fastlock_recall",
                    index % ARRAY_SIZE(frequencies_hz))) < 0) {
            fprintf(stderr, "frame %u tune failed: %s\n", index, strerror(errno));
            return -1;
        }
        after = now_seconds();
        tune.values[index] = after - before;
        sleep_microseconds(SETTLE_US);

        before = now_seconds();
        buffer = metadata_mode
            ? iio_device_create_buffer_with_metadata(rx, buffer_samples,
                tandem_hold_request, sizeof(tandem_hold_request))
            : iio_device_create_buffer(rx, buffer_samples, false);
        after = now_seconds();
        create.values[index] = after - before;
        if (!buffer) {
            fprintf(stderr, "frame %u metadata buffer create failed: %s\n",
                index, strerror(errno));
            return -1;
        }

        for (refill_index = 0; refill_index < refills_per_target; ++refill_index) {
            metadata_bytes = 0;
            before = now_seconds();
            refill_bytes = metadata_mode
                ? iio_buffer_refill_with_metadata(buffer, metadata,
                    sizeof(metadata), &metadata_bytes)
                : iio_buffer_refill(buffer);
            after = now_seconds();
            refill_total += after - before;
            if (refill_bytes < 0 || (size_t)refill_bytes != buffer_samples * 8U) {
                fprintf(stderr, "frame %u refill failed/mismatched: %zd (%s)\n",
                    index, refill_bytes,
                    refill_bytes < 0 ? strerror((int)-refill_bytes) : "size");
                iio_buffer_destroy(buffer);
                return -1;
            }
            if (metadata_mode && validate_metadata(metadata, metadata_bytes,
                    buffer_samples, stream_ids, index) < 0) {
                fprintf(stderr, "frame %u metadata attestation failed\n", index);
                iio_buffer_destroy(buffer);
                return -1;
            }

            before = now_seconds();
            start = iio_buffer_start(buffer);
            end = iio_buffer_end(buffer);
            bytes = (size_t)(end - start);
            if (bytes != buffer_samples * 8U) {
                fprintf(stderr, "frame %u local IQ buffer size mismatch\n", index);
                iio_buffer_destroy(buffer);
                return -1;
            }
            payload_bytes += bytes;
            *checksum = (*checksum ^ start[0]) * 16777619U;
            *checksum = (*checksum ^ start[bytes / 2U]) * 16777619U;
            *checksum = (*checksum ^ start[bytes - 1U]) * 16777619U;
            after = now_seconds();
            touch_total += after - before;
        }
        refill.values[index] = refill_total;
        touch.values[index] = touch_total;

        before = now_seconds();
        iio_buffer_destroy(buffer);
        after = now_seconds();
        destroy.values[index] = after - before;
        whole.values[index] = now_seconds() - frame_start;
    }
    wall_seconds = now_seconds() - run_start;

    printf("    {\n");
    printf("      \"sample_rate_hz\": %lld,\n", sample_rate);
    printf("      \"rf_bandwidth_hz\": %lld,\n", sample_rate);
    printf("      \"dwell_samples_per_channel\": %zu,\n", dwell_samples);
    printf("      \"buffer_samples_per_channel\": %zu,\n", buffer_samples);
    printf("      \"refills_per_target\": %u,\n", refills_per_target);
    printf("      \"frames_completed\": %u,\n", FRAMES_PER_RATE);
    printf("      \"full_scans_completed\": %u,\n",
        FRAMES_PER_RATE / (unsigned int)ARRAY_SIZE(frequencies_hz));
    printf("      \"listen_seconds\": %.9f,\n",
        FRAMES_PER_RATE * DWELL_MS / 1000.0);
    printf("      \"wall_seconds\": %.9f,\n", wall_seconds);
    printf("      \"listening_duty_cycle\": %.9f,\n",
        (FRAMES_PER_RATE * DWELL_MS / 1000.0) / wall_seconds);
    printf("      \"payload_bytes_acquired\": %" PRIu64 ",\n", payload_bytes);
    printf("      \"timings\": {\n");
    print_stats("tune", &tune, true);
    print_stats("buffer_create", &create, true);
    print_stats("buffer_refill", &refill, true);
    print_stats("payload_touch", &touch, true);
    print_stats("buffer_destroy", &destroy, true);
    print_stats("whole_target", &whole, false);
    printf("      }\n");
    printf("    }");
    return 0;
}

int main(int argc, char **argv)
{
    struct iio_context *context = NULL;
    struct iio_device *phy, *rx;
    struct iio_channel *lo, *rx_phy[2];
    struct preserved_settings original = {0};
    const char *serial;
    uint32_t checksum = 2166136261U;
    unsigned int channel_index, rate_index;
    static const long long sample_rates[] = {2500000LL, 5000000LL};
    bool metadata_mode = true;
    unsigned int refill_ms = DWELL_MS;
    int ret = EXIT_FAILURE;
    bool preserved = false;

    if (argc == 2 && !strcmp(argv[1], "ordinary-local"))
        metadata_mode = false;
    else if (argc == 2 && !strcmp(argv[1], "ordinary-local-small-buffer")) {
        metadata_mode = false;
        refill_ms = 10U;
    }
    else if (argc != 1) {
        fprintf(stderr, "usage: %s [ordinary-local|ordinary-local-small-buffer]\n",
            argv[0]);
        goto out;
    }
    /* The release metadata provider is an iiOD service. Loopback keeps the
     * protocol, control, and IQ traffic on the radio without Ethernet cost.
     * The ordinary ceiling mode uses the direct Linux IIO backend. */
    context = metadata_mode
        ? iio_create_context_from_uri("ip:127.0.0.1")
        : iio_create_local_context();
    if (!context) {
        perror("iio context creation");
        goto out;
    }
    serial = iio_context_get_attr_value(context, "hw_serial");
    if (!serial || strcmp(serial, EXPECTED_SERIAL)) {
        fprintf(stderr, "refusing radio serial %s; expected %s\n",
            serial ? serial : "(absent)", EXPECTED_SERIAL);
        goto out;
    }
    phy = iio_context_find_device(context, "ad9361-phy");
    rx = iio_context_find_device(context, "cf-ad9361-lpc");
    if (!phy || !rx) {
        fprintf(stderr, "required IIO devices missing\n");
        goto out;
    }
    lo = iio_device_find_channel(phy, "altvoltage0", true);
    rx_phy[0] = iio_device_find_channel(phy, "voltage0", false);
    rx_phy[1] = iio_device_find_channel(phy, "voltage1", false);
    if (!lo || !rx_phy[0] || !rx_phy[1]) {
        fprintf(stderr, "required PHY channels missing\n");
        goto out;
    }
    if (preserve_settings(lo, rx_phy, &original) < 0) {
        fprintf(stderr, "failed to preserve radio settings\n");
        goto out;
    }
    preserved = true;

    for (channel_index = 0; channel_index < iio_device_get_channels_count(rx);
            ++channel_index) {
        struct iio_channel *channel = iio_device_get_channel(rx, channel_index);
        if (iio_channel_is_scan_element(channel) && !iio_channel_is_output(channel))
            iio_channel_enable(channel);
    }
    if (iio_device_get_sample_size(rx) != 8) {
        fprintf(stderr, "expected dual-RX 8-byte scan step, got %zd\n",
            iio_device_get_sample_size(rx));
        goto restore;
    }
    if (iio_device_set_kernel_buffers_count(rx, metadata_mode ? 8U : 1U) < 0) {
        fprintf(stderr, "failed to set capture kernel-buffer depth: %s\n",
            strerror(errno));
        goto restore;
    }
    for (channel_index = 0; channel_index < 2; ++channel_index) {
        if (iio_channel_attr_write(rx_phy[channel_index], "gain_control_mode",
                "manual") < 0 ||
            iio_channel_attr_write_double(rx_phy[channel_index], "hardwaregain",
                40.0) < 0) {
            fprintf(stderr, "failed to configure manual 40 dB gain\n");
            goto restore;
        }
    }
    if (!metadata_mode && prepare_fastlock_profiles(lo) < 0)
        goto restore;

    printf("{\n");
    printf("  \"implementation\": \"%s\",\n", metadata_mode
        ? "pluto-loopback-iiod-c-metadata-abi3-prototype"
        : "pluto-local-c-ordinary-dma-ceiling-prototype");
    printf("  \"radio_serial\": \"%s\",\n", serial);
    printf("  \"dwell_ms\": %u,\n", DWELL_MS);
    printf("  \"settle_guard_us\": %u,\n", SETTLE_US);
    printf("  \"tune_mode\": \"%s\",\n",
        metadata_mode ? "ordinary-frequency-write" : "volatile-ad9361-fastlock-recall");
    printf("  \"iq_transport_or_persistence_included\": false,\n");
    printf("  \"rates\": [\n");
    for (rate_index = 0; rate_index < ARRAY_SIZE(sample_rates); ++rate_index) {
        if (run_rate(rx, lo, rx_phy, sample_rates[rate_index], metadata_mode,
                refill_ms, &checksum) < 0) {
            printf("\n");
            goto restore;
        }
        printf("%s\n", rate_index + 1U < ARRAY_SIZE(sample_rates) ? "," : "");
    }
    printf("  ],\n");
    printf("  \"checksum\": %u,\n", checksum);
    if (metadata_mode)
        printf("  \"metadata_attestation\": "
               "\"all frames CRC-valid, exact-size, gap-free, overflow-free, unique-stream\"\n");
    else
        printf("  \"metadata_attestation\": null,\n"
               "  \"qualification\": "
               "\"timing ceiling only; ordinary DMA cannot satisfy the scanner continuity contract\"\n");
    printf("}\n");
    ret = EXIT_SUCCESS;

restore:
    if (preserved)
        restore_settings(lo, rx_phy, &original);
out:
    if (context)
        iio_context_destroy(context);
    return ret;
}
