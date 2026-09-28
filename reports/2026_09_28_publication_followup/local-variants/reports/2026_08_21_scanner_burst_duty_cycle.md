# Scanner burst duty-cycle review

Date: 2026-08-21

Scope: ten newest complete four-scan bursts in the local production scanner store

Source: immutable manifests beneath `/srv/bulk/leo/scanner-recordings`

## Result

Each burst contains four complete scans. Each scan covers eight Starlink
channel/edge targets and records 80 ms per target at 2.5 Msps. RX0 and RX1 are
captured simultaneously, so receiver time is not double-counted when computing
radio duty cycle.

- Recorded duration per scan: `8 * 0.080 s = 0.640 s`
- Recorded duration per four-scan burst: `4 * 0.640 s = 2.560 s`
- Mean within-burst RF duty cycle: **48.44%**
- Mean individual-scan RF duty cycle: **68.28%**
- Mean capture-to-durable duty cycle: **26.51%**

The burst RF duty is highly repeatable: its sample standard deviation is 0.42
percentage points, its range is 1.35 percentage points, and its coefficient of
variation is 0.88%.

## Definitions

Three related measurements are reported separately:

1. **Recorded time** is the sum of `sample_count / sample_rate_hz` over the
   manifest's frames. It measures requested RF sample time and does not count
   simultaneous receivers twice.
2. **RF capture span** runs from the earliest
   `host_request_utc_ns_lower` to the latest `host_request_utc_ns_upper` in the
   burst. RF duty is `recorded time / RF capture span`.
3. **Durable span** runs from the earliest manifest `created_utc_ns` to the
   latest `finalized_utc_ns` in the burst. It includes compression, hashing,
   fsync, and atomic bundle publication. Durable duty is
   `recorded time / durable span`.

The individual-scan duty column is the mean of the four values computed as
`0.640 s / scan RF capture span`. It shows tuning/listening efficiency inside
each scan, while burst RF duty additionally includes handoff gaps between the
four scans.

## Latest ten bursts

Times are UTC.

| Burst | Start | Radio | Recorded | RF capture span | RF duty | Mean individual-scan duty | Durable span | Durable duty |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| `7e619cb033db4180` | 22:43:20.863 | 5d4d | 2.560 s | 5.331 s | 48.02% | 67.49% | 10.067 s | 25.43% |
| `5245b3272a2c4280` | 22:39:26.252 | 19f2 | 2.560 s | 5.259 s | 48.68% | 68.22% | 9.774 s | 26.19% |
| `2c0ca1426de546ef` | 22:29:33.188 | 5d4d | 2.560 s | 5.369 s | 47.68% | 67.53% | 9.680 s | 26.45% |
| `56e2f8dff6a04dd2` | 22:25:15.563 | 19f2 | 2.560 s | 5.221 s | 49.03% | 69.95% | 10.059 s | 25.45% |
| `ec9fa603b96a495a` | 22:21:03.073 | 19f2 | 2.560 s | 5.248 s | 48.78% | 68.35% | 10.272 s | 24.92% |
| `b144bd37d7894d73` | 22:17:06.471 | 5d4d | 2.560 s | 5.260 s | 48.67% | 68.35% | 9.331 s | 27.44% |
| `05e62a10f89e4c9c` | 22:06:00.124 | 19f2 | 2.560 s | 5.298 s | 48.32% | 68.86% | 9.568 s | 26.76% |
| `89d7537ed6a2402e` | 22:01:42.800 | 5d4d | 2.560 s | 5.316 s | 48.16% | 68.41% | 9.556 s | 26.79% |
| `7e43a601dd8d4816` | 21:57:30.032 | 5d4d | 2.560 s | 5.308 s | 48.23% | 67.38% | 8.965 s | 28.56% |
| `effe5d13c2cf47b3` | 21:53:34.167 | 19f2 | 2.560 s | 5.243 s | 48.83% | 68.29% | 9.425 s | 27.16% |

## Aggregate statistics

| Metric | Minimum | Mean | Median | Maximum |
|---|---:|---:|---:|---:|
| Recorded time per burst | 2.560 s | 2.560 s | 2.560 s | 2.560 s |
| RF capture span | 5.221 s | 5.285 s | 5.279 s | 5.369 s |
| RF duty cycle | 47.68% | 48.44% | 48.50% | 49.03% |
| Mean individual-scan duty | 67.38% | 68.28% | 68.32% | 69.95% |
| Durable span | 8.965 s | 9.670 s | 9.624 s | 10.272 s |
| Durable duty cycle | 24.92% | 26.51% | 26.60% | 28.56% |

The ten bursts span 2,992.027 seconds from the first RF request in the oldest
burst to the final RF response in the newest burst. They contain 25.6 seconds
of requested RF samples, giving an overall calendar scanner duty cycle of
**0.856%** across that observation interval.

## Interpretation

A typical individual scan records 640 ms over approximately 940 ms, so about
68% of its RF capture span contains requested samples. A four-scan burst
records 2.56 s over approximately 5.29 s, reducing duty to about 48% after the
handoffs between scans are included.

Durable publication finishes in approximately 9.67 s on average. The gap
between the RF span and durable span is storage work rather than lost samples:
compression, checksums, manifest creation, fsync, and atomic publication occur
after acquisition. If scanner cadence needs to increase further, RF handoff
overhead and durable publication should be measured and optimized separately.

## Reproduction method

For each complete `scan-burst-*` group, the review:

1. grouped the four `-01` through `-04` manifests by burst prefix;
2. required exactly four manifests;
3. summed frame duration from authoritative `sample_count` and
   `configuration.sample_rate_hz`;
4. computed RF span from the frame request bounds;
5. computed durable span from manifest creation/finalization bounds; and
6. sorted groups by RF start time and selected the newest ten.

No IQ payload was decoded or modified. No catalog, service, radio, or QNAP
state was changed during this read-only review.

## Live Pluto+ burst-retune benchmark

The manifest review above describes the production scanner. A separate bounded
hardware experiment measured the lower-level cost of stopping acquisition,
retuning, and returning one frequency-pure 80 ms IQ frame through three libiio
execution paths. These figures are not recomputed from the production scanner
manifests and should not be substituted for the production results above.

### Question and duty-cycle definition

The experiment asks how much wall-clock time is occupied by known-frequency IQ
when every 80 ms frame uses a different center frequency. Listening duty cycle
is defined as:

```text
completed frames * samples per frame / sample rate
---------------------------------------------------
                 elapsed wall time
```

The test accumulated exactly 6.0 seconds of IQ in each implementation, then
measured how much wall time was needed. This is equivalent to estimating how
much valid capture time each implementation could deliver in a fixed six-second
wall interval.

### Radio and host

- Host: `gauss`
- IP URI: `ip:192.168.1.14`
- USB URI: `usb:5.2.5`
- Pluto+ serial: `winbond-db620818a328172c`
- Firmware: `v0.40-plutoplus-spf-tandem-agc-v7`
- Host libiio: v0.26
- Local Pluto libiio: v0.25

The IP and USB context attributes reported the same serial number and firmware,
confirming that all three paths exercised the same physical radio.

### Acquisition configuration

- Five frequencies: 900, 950, 1000, 1050, and 1100 MHz
- 50 MHz frequency spacing, all in the same AD9361 gain-table region
- Shuffled/permuted order with no adjacent repeated frequency
- 80 ms per frame
- 75 frames, exactly 6.0 seconds of accumulated IQ
- 3,000,000 samples/s
- Dual RX enabled
- 1,500,000 Hz RF bandwidth
- 240,000 samples per channel per frame
- 1,920,000 bytes per dual-RX frame
- 144,000,000 bytes total payload
- Normal LO tuning, without fastlock
- 250 us guard after the frequency attribute write returns
- One kernel buffer
- Buffer destroyed and recreated after each retune

One kernel buffer was intentional. A 16- or 32-buffer kernel queue can already
contain samples acquired at the previous frequency and therefore makes the
frequency label of the next returned frame ambiguous. A future 16/32-frame
queue should be a userspace pool of completed, frequency-labelled frames rather
than a pre-retune kernel backlog.

### Results

| Implementation | Wall time for 6.0 s IQ | Listening duty | IQ in 6 s wall time | Mean frame time | Effective payload |
|---|---:|---:|---:|---:|---:|
| C/libiio running locally on Pluto+ | 6.719 s | **89.30%** | about 5.36 s | 89.58 ms | 20.44 MiB/s |
| Python/libiio over IP | 9.266 s | **64.75%** | about 3.89 s | 123.54 ms | 14.82 MiB/s |
| Python/libiio over USB | 17.575 s | **34.14%** | about 2.05 s | 234.33 ms | 7.81 MiB/s |

All 75 frames completed in every run. A separate ten-frame USB repeat measured
33.89% duty, confirming that the low USB result was repeatable rather than a
single transient.

### Timing breakdown

All values below are means across the 75 frames.

| Operation | Local C | Python/IP | Python/USB |
|---|---:|---:|---:|
| LO attribute write | 1.286 ms | 1.864 ms | 2.148 ms |
| Buffer creation | 6.959 ms | 8.049 ms | 89.009 ms |
| Buffer refill | 80.001 ms | 108.616 ms | 138.398 ms |
| Userspace payload copy/touch | 0.002 ms | 0.840 ms | 0.994 ms |
| Buffer destruction | 0.999 ms | 3.730 ms | 3.383 ms |
| Whole frame | 89.584 ms | 123.542 ms | 234.328 ms |

LO retuning itself was generally short:

| Path | Tune median | Tune p95 | Tune p99 | Tune maximum |
|---|---:|---:|---:|---:|
| Local C | 1.023 ms | 1.079 ms | 6.329 ms | 19.585 ms |
| Python/IP | 1.410 ms | 2.374 ms | 13.045 ms | 20.853 ms |
| Python/USB | 1.400 ms | 4.920 ms | 10.058 ms | 20.062 ms |

The dominant USB penalty in this stop/recreate implementation is not the LO
write. Repeated USB buffer creation cost about 89 ms per frame and refill cost
about 138 ms, including the 80 ms acquisition. IP avoided most of the creation
penalty but still synchronously transported the frame through the remote
context. Local C kept refill at almost exactly the requested 80 ms.

### Recommended implementation

The local C implementation is the appropriate foundation for the scanner:

1. An acquisition thread selects the next frequency, writes the LO, waits the
   explicit guard, creates/fills one 80 ms buffer, and attaches metadata.
2. Each completed frame records at least the frequency, sample rate, sequence
   number, monotonic capture time, and any invalid-prefix/settling allowance.
3. A separate sender thread transfers completed frames to the host.
4. A bounded userspace pool holds 16 or 32 completed frames. If the sender falls
   behind, completed frames may be dropped without blocking acquisition.

At this dual-RX configuration, the sender must sustain approximately 21.4 MB/s
averaged over wall time to retain every locally captured frame. Sending must not
be performed synchronously in the acquisition loop. A deliberately scalar
full-frame checksum on the Pluto ARM increased the local run from 6.72 seconds
to 15.70 seconds, demonstrating why payload processing belongs in a separate
thread or optimized bulk operation.

Fastlock may reduce the normal approximately 1 ms tune latency and its cold
outliers, but it cannot address the much larger remote buffer and transport
costs. It is therefore an optimization after the local acquisition/sender split,
not a substitute for that architecture.

### Measurement limitation

Every refill returned the expected amount of real IQ data and the AD9361 driver
completed each frequency write before capture began. However, no calibrated
multi-frequency RF source was injected during this run. The benchmark therefore
measures sample-active duty after the driver tune operation plus a 250 us guard;
it does not independently prove, at the signal level, which exact first sample
is free of retune transient. A second SDR or synthesizer emitting known tones at
the five targets should be used to measure the invalid prefix before reducing
the guard.

After the tests, the original LO, sample-rate, and bandwidth configuration was
restored. The `tandem-agc` device reported idle state, zero fault flags, and zero
overflows.

## Live benchmark code

### Python remote-context benchmark

The same program is used for IP and USB by changing `--uri`:

```bash
python3 scan_duty_bench.py --uri ip:192.168.1.14
python3 scan_duty_bench.py --uri usb:5.2.5
```

```python
#!/usr/bin/env python3
"""Measure burst-scan listening duty cycle through a remote libiio context."""

import argparse
import gc
import json
import random
import statistics
import time

import iio


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    position = fraction * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def shuffled_slots(count, frame_count, seed):
    rng = random.Random(seed)
    result = []
    previous = None
    while len(result) < frame_count:
        sweep = list(range(count))
        rng.shuffle(sweep)
        if previous is not None and sweep[0] == previous and len(sweep) > 1:
            sweep[0], sweep[1] = sweep[1], sweep[0]
        result.extend(sweep)
        previous = sweep[-1]
    return result[:frame_count]


def set_attr(channel, name, value):
    channel.attrs[name].value = str(value)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True)
    parser.add_argument("--sample-rate", type=int, default=3_000_000)
    parser.add_argument("--bandwidth", type=int, default=1_500_000)
    parser.add_argument("--frame-ms", type=float, default=80.0)
    parser.add_argument("--frames", type=int, default=75)
    parser.add_argument("--settle-us", type=int, default=250)
    parser.add_argument("--seed", type=int, default=12345)
    parser.add_argument(
        "--frequencies",
        default="900000000,950000000,1000000000,1050000000,1100000000",
    )
    args = parser.parse_args()

    frequencies = [int(item) for item in args.frequencies.split(",")]
    frame_samples = round(args.sample_rate * args.frame_ms / 1000.0)
    requested_listen_seconds = args.frames * frame_samples / args.sample_rate
    slots = shuffled_slots(len(frequencies), args.frames, args.seed)

    context = iio.Context(args.uri)
    context.set_timeout(15_000)
    phy = context.find_device("ad9361-phy")
    rx = context.find_device("cf-ad9361-lpc")
    if phy is None or rx is None:
        raise RuntimeError("required ad9361-phy/cf-ad9361-lpc device missing")

    rx_lo = phy.find_channel("altvoltage0", True)
    rx_phy = phy.find_channel("voltage0", False)
    if rx_lo is None or rx_phy is None:
        raise RuntimeError("required RX LO/PHY channel missing")

    scan_channels = [
        channel
        for channel in rx.channels
        if channel.scan_element and not channel.output
    ]
    if len(scan_channels) < 4:
        raise RuntimeError("dual-RX scan channels missing")

    original = {
        "frequency": rx_lo.attrs["frequency"].value,
        "sampling_frequency": rx_phy.attrs["sampling_frequency"].value,
        "rf_bandwidth": rx_phy.attrs["rf_bandwidth"].value,
    }
    for channel in scan_channels:
        channel.enabled = True

    tune_times = []
    create_times = []
    refill_times = []
    copy_times = []
    destroy_times = []
    frame_times = []
    payload_bytes = 0
    checksum = 0
    completed = 0

    try:
        set_attr(rx_phy, "sampling_frequency", args.sample_rate)
        set_attr(rx_phy, "rf_bandwidth", args.bandwidth)
        rx.set_kernel_buffers_count(1)

        run_start = time.perf_counter_ns()
        for frame_index, slot in enumerate(slots):
            frame_start = time.perf_counter_ns()

            before = time.perf_counter_ns()
            set_attr(rx_lo, "frequency", frequencies[slot])
            after = time.perf_counter_ns()
            tune_times.append((after - before) / 1e9)

            time.sleep(args.settle_us / 1e6)

            before = time.perf_counter_ns()
            buffer = iio.Buffer(rx, frame_samples, False)
            after = time.perf_counter_ns()
            create_times.append((after - before) / 1e9)

            before = time.perf_counter_ns()
            buffer.refill()
            after = time.perf_counter_ns()
            refill_times.append((after - before) / 1e9)

            before = time.perf_counter_ns()
            payload = buffer.read()
            after = time.perf_counter_ns()
            copy_times.append((after - before) / 1e9)
            payload_bytes += len(payload)
            if payload:
                checksum = (checksum + payload[0] + payload[-1] + frame_index) & 0xFFFFFFFF

            before = time.perf_counter_ns()
            del payload
            del buffer
            gc.collect()
            after = time.perf_counter_ns()
            destroy_times.append((after - before) / 1e9)

            completed += 1
            frame_times.append((time.perf_counter_ns() - frame_start) / 1e9)

        wall_seconds = (time.perf_counter_ns() - run_start) / 1e9
    finally:
        set_attr(rx_phy, "rf_bandwidth", original["rf_bandwidth"])
        set_attr(rx_phy, "sampling_frequency", original["sampling_frequency"])
        set_attr(rx_lo, "frequency", original["frequency"])

    actual_listen_seconds = completed * frame_samples / args.sample_rate

    def stats(values):
        return {
            "mean_ms": statistics.fmean(values) * 1000.0,
            "p50_ms": percentile(values, 0.50) * 1000.0,
            "p95_ms": percentile(values, 0.95) * 1000.0,
            "p99_ms": percentile(values, 0.99) * 1000.0,
            "max_ms": max(values) * 1000.0,
        }

    result = {
        "implementation": "python-libiio-remote",
        "uri": args.uri,
        "context_description": context.description,
        "sample_rate_hz": args.sample_rate,
        "rf_bandwidth_hz": args.bandwidth,
        "frame_samples_per_channel": frame_samples,
        "frame_listen_ms": frame_samples / args.sample_rate * 1000.0,
        "frames_requested": args.frames,
        "frames_completed": completed,
        "frequencies_hz": frequencies,
        "settle_guard_us": args.settle_us,
        "requested_listen_seconds": requested_listen_seconds,
        "actual_listen_seconds": actual_listen_seconds,
        "wall_seconds": wall_seconds,
        "listening_duty_cycle": actual_listen_seconds / wall_seconds,
        "payload_bytes": payload_bytes,
        "effective_payload_mib_s": payload_bytes / wall_seconds / (1024.0 * 1024.0),
        "checksum": checksum,
        "tune": stats(tune_times),
        "buffer_create": stats(create_times),
        "buffer_refill": stats(refill_times),
        "buffer_copy": stats(copy_times),
        "buffer_destroy": stats(destroy_times),
        "whole_frame": stats(frame_times),
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
```

### Pluto-local C benchmark

The C program is cross-compiled against the Pluto firmware staging sysroot,
copied to the radio, and executed over SSH. The benchmark uses sparse payload
touches so it measures local acquisition/control rather than a deliberately
scalar 144 MB checksum.

```c
// SPDX-License-Identifier: GPL-2.0-or-later
/* Measure tune/settle/single-buffer capture duty cycle locally on Pluto+. */

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
#include <unistd.h>

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define FRAMES 75U
#define SAMPLE_RATE 3000000LL
#define RF_BANDWIDTH 1500000LL
#define FRAME_SAMPLES 240000U
#define SETTLE_US 250U

static const long long frequencies[] = {
    900000000LL, 950000000LL, 1000000000LL, 1050000000LL, 1100000000LL,
};

struct timings {
    double values[FRAMES];
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

static int compare_double(const void *left, const void *right)
{
    const double a = *(const double *)left;
    const double b = *(const double *)right;
    return (a > b) - (a < b);
}

static double quantile(const struct timings *input, double fraction)
{
    double values[FRAMES];
    double position, weight;
    unsigned int lower, upper;

    memcpy(values, input->values, sizeof(values));
    qsort(values, FRAMES, sizeof(values[0]), compare_double);
    position = fraction * (FRAMES - 1U);
    lower = (unsigned int)position;
    upper = lower + 1U < FRAMES ? lower + 1U : lower;
    weight = position - lower;
    return values[lower] * (1.0 - weight) + values[upper] * weight;
}

static double maximum(const struct timings *input)
{
    double result = input->values[0];
    unsigned int index;
    for (index = 1; index < FRAMES; ++index)
        if (input->values[index] > result)
            result = input->values[index];
    return result;
}

static double mean(const struct timings *input)
{
    double sum = 0.0;
    unsigned int index;
    for (index = 0; index < FRAMES; ++index)
        sum += input->values[index];
    return sum / FRAMES;
}

static void print_stats(const char *name, const struct timings *values, bool comma)
{
    printf("    \"%s\": {\"mean_ms\": %.6f, \"p50_ms\": %.6f, "
           "\"p95_ms\": %.6f, \"p99_ms\": %.6f, \"max_ms\": %.6f}%s\n",
           name, mean(values) * 1000.0, quantile(values, 0.50) * 1000.0,
           quantile(values, 0.95) * 1000.0, quantile(values, 0.99) * 1000.0,
           maximum(values) * 1000.0, comma ? "," : "");
}

int main(void)
{
    struct iio_context *context = NULL;
    struct iio_device *phy, *rx;
    struct iio_channel *lo, *rx_phy;
    struct timings tune = {0}, create = {0}, refill = {0}, payload_touch = {0};
    struct timings destroy = {0}, whole_frame = {0};
    char original_lo[64], original_rate[64], original_bw[64];
    uint8_t slot_order[FRAMES];
    uint32_t checksum = 2166136261U;
    uint64_t payload_bytes = 0;
    double run_start, wall_seconds, before, after, frame_start;
    unsigned int index, channel_index;
    int ret = EXIT_FAILURE;

    context = iio_create_local_context();
    if (!context) {
        perror("iio_create_local_context");
        goto out;
    }
    phy = iio_context_find_device(context, "ad9361-phy");
    rx = iio_context_find_device(context, "cf-ad9361-lpc");
    if (!phy || !rx) {
        fprintf(stderr, "required IIO devices missing\n");
        goto out;
    }
    lo = iio_device_find_channel(phy, "altvoltage0", true);
    rx_phy = iio_device_find_channel(phy, "voltage0", false);
    if (!lo || !rx_phy) {
        fprintf(stderr, "required PHY channels missing\n");
        goto out;
    }
    if (iio_channel_attr_read(lo, "frequency", original_lo,
            sizeof(original_lo)) < 0 ||
        iio_channel_attr_read(rx_phy, "sampling_frequency", original_rate,
            sizeof(original_rate)) < 0 ||
        iio_channel_attr_read(rx_phy, "rf_bandwidth", original_bw,
            sizeof(original_bw)) < 0) {
        fprintf(stderr, "failed to preserve radio configuration\n");
        goto out;
    }

    for (channel_index = 0; channel_index < iio_device_get_channels_count(rx);
            ++channel_index) {
        struct iio_channel *channel = iio_device_get_channel(rx, channel_index);
        if (iio_channel_is_scan_element(channel) &&
            !iio_channel_is_output(channel))
            iio_channel_enable(channel);
    }
    if (iio_device_get_sample_size(rx) != 8) {
        fprintf(stderr, "expected dual-RX 8-byte scan step, got %zd\n",
            iio_device_get_sample_size(rx));
        goto restore;
    }
    if (iio_channel_attr_write_longlong(rx_phy, "sampling_frequency",
            SAMPLE_RATE) < 0 ||
        iio_channel_attr_write_longlong(rx_phy, "rf_bandwidth",
            RF_BANDWIDTH) < 0 ||
        iio_device_set_kernel_buffers_count(rx, 1) < 0) {
        fprintf(stderr, "failed to configure RX\n");
        goto restore;
    }

    /* Deterministic permutation; adjacent frames always differ. */
    for (index = 0; index < FRAMES; ++index) {
        static const uint8_t sweep[5] = {2, 0, 4, 1, 3};
        slot_order[index] = sweep[index % ARRAY_SIZE(sweep)];
    }

    run_start = now_seconds();
    for (index = 0; index < FRAMES; ++index) {
        struct iio_buffer *buffer;
        const uint8_t *cursor, *end;
        size_t bytes;

        frame_start = now_seconds();
        before = now_seconds();
        if (iio_channel_attr_write_longlong(lo, "frequency",
                frequencies[slot_order[index]]) < 0) {
            fprintf(stderr, "frame %u tune failed: %s\n", index, strerror(errno));
            goto restore;
        }
        after = now_seconds();
        tune.values[index] = after - before;
        sleep_microseconds(SETTLE_US);

        before = now_seconds();
        buffer = iio_device_create_buffer(rx, FRAME_SAMPLES, false);
        after = now_seconds();
        create.values[index] = after - before;
        if (!buffer) {
            fprintf(stderr, "frame %u buffer create failed: %s\n",
                index, strerror(errno));
            goto restore;
        }

        before = now_seconds();
        if (iio_buffer_refill(buffer) < 0) {
            fprintf(stderr, "frame %u refill failed: %s\n", index, strerror(errno));
            iio_buffer_destroy(buffer);
            goto restore;
        }
        after = now_seconds();
        refill.values[index] = after - before;

        before = now_seconds();
        cursor = iio_buffer_start(buffer);
        end = iio_buffer_end(buffer);
        bytes = (size_t)(end - cursor);
        payload_bytes += bytes;
        /* Prove that a real frame returned without charging a scalar full-frame
         * checksum to acquisition. A sender can consume completed buffers on a
         * separate thread in the eventual application. */
        if (bytes) {
            checksum ^= cursor[0];
            checksum *= 16777619U;
            checksum ^= cursor[bytes / 2U];
            checksum *= 16777619U;
            checksum ^= cursor[bytes - 1U];
            checksum *= 16777619U;
        }
        after = now_seconds();
        payload_touch.values[index] = after - before;

        before = now_seconds();
        iio_buffer_destroy(buffer);
        after = now_seconds();
        destroy.values[index] = after - before;
        whole_frame.values[index] = now_seconds() - frame_start;
    }
    wall_seconds = now_seconds() - run_start;
    ret = EXIT_SUCCESS;

    printf("{\n");
    printf("  \"implementation\": \"c-libiio-local\",\n");
    printf("  \"sample_rate_hz\": %lld,\n", SAMPLE_RATE);
    printf("  \"rf_bandwidth_hz\": %lld,\n", RF_BANDWIDTH);
    printf("  \"frame_samples_per_channel\": %u,\n", FRAME_SAMPLES);
    printf("  \"frame_listen_ms\": 80.0,\n");
    printf("  \"frames_completed\": %u,\n", FRAMES);
    printf("  \"settle_guard_us\": %u,\n", SETTLE_US);
    printf("  \"actual_listen_seconds\": 6.0,\n");
    printf("  \"wall_seconds\": %.9f,\n", wall_seconds);
    printf("  \"listening_duty_cycle\": %.9f,\n", 6.0 / wall_seconds);
    printf("  \"payload_bytes\": %" PRIu64 ",\n", payload_bytes);
    printf("  \"effective_payload_mib_s\": %.9f,\n",
        payload_bytes / wall_seconds / (1024.0 * 1024.0));
    printf("  \"checksum\": %u,\n", checksum);
    printf("  \"timings\": {\n");
    print_stats("tune", &tune, true);
    print_stats("buffer_create", &create, true);
    print_stats("buffer_refill", &refill, true);
    print_stats("payload_touch", &payload_touch, true);
    print_stats("buffer_destroy", &destroy, true);
    print_stats("whole_frame", &whole_frame, false);
    printf("  }\n");
    printf("}\n");

restore:
    (void)iio_channel_attr_write(rx_phy, "rf_bandwidth", original_bw);
    (void)iio_channel_attr_write(rx_phy, "sampling_frequency", original_rate);
    (void)iio_channel_attr_write(lo, "frequency", original_lo);
out:
    if (context)
        iio_context_destroy(context);
    return ret;
}
```
