#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64

#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <sched.h>
#include <signal.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

enum {
    MAX_JOBS = 600,
    MAX_DURATION_MS = 90000,
    ALARM_SECONDS = 120,
};

static const uint64_t MAX_TOTAL_BYTES = UINT64_C(1500000000);

static double millis(clockid_t clock_id)
{
    struct timespec now;
    if (clock_gettime(clock_id, &now) != 0) {
        return -1.0;
    }
    return (double)now.tv_sec * 1000.0 + (double)now.tv_nsec / 1000000.0;
}

static int sleep_until(double deadline_ms)
{
    double seconds = floor(deadline_ms / 1000.0);
    struct timespec deadline = {
        .tv_sec = (time_t)seconds,
        .tv_nsec = (long)((deadline_ms - seconds * 1000.0) * 1000000.0),
    };
    int result;
    do {
        result = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &deadline, NULL);
    } while (result == EINTR);
    return result;
}

static bool parse_unsigned(const char *text, unsigned *result)
{
    char *end = NULL;
    errno = 0;
    unsigned long value = strtoul(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value > UINT32_MAX) {
        return false;
    }
    *result = (unsigned)value;
    return true;
}

static bool parse_core(const char *text, int *result)
{
    char *end = NULL;
    errno = 0;
    long value = strtol(text, &end, 10);
    if (errno != 0 || end == text || *end != '\0' || value < 0 || value >= CPU_SETSIZE) {
        return false;
    }
    *result = (int)value;
    return true;
}

static bool parse_period(const char *text, double *result)
{
    char *end = NULL;
    errno = 0;
    double value = strtod(text, &end);
    if (errno != 0 || end == text || *end != '\0' || !isfinite(value) || value < 120.0) {
        return false;
    }
    *result = value;
    return true;
}

static int read_full(int descriptor, uint8_t *buffer, size_t size)
{
    size_t offset = 0;
    while (offset < size) {
        ssize_t count = read(descriptor, buffer + offset, size - offset);
        if (count > 0) {
            offset += (size_t)count;
        } else if (count == 0) {
            errno = EIO;
            return -1;
        } else if (errno != EINTR) {
            return -1;
        }
    }
    return 0;
}

static int write_full(int descriptor, const uint8_t *buffer, size_t size)
{
    size_t offset = 0;
    while (offset < size) {
        ssize_t count = write(descriptor, buffer + offset, size - offset);
        if (count > 0) {
            offset += (size_t)count;
        } else if (count == 0) {
            errno = EIO;
            return -1;
        } else if (errno != EINTR) {
            return -1;
        }
    }
    return 0;
}

static void usage(const char *program)
{
    fprintf(stderr, "usage: %s INPUT OUTPUT JOBS PERIOD_MS CORE\n", program);
}

int main(int argc, char **argv)
{
    if (argc != 6) {
        usage(argv[0]);
        return 2;
    }

    unsigned jobs = 0;
    double period_ms = 0.0;
    int core = -1;
    if (!parse_unsigned(argv[3], &jobs) || jobs < 1 || jobs > MAX_JOBS ||
        !parse_period(argv[4], &period_ms) ||
        (double)jobs * period_ms > (double)MAX_DURATION_MS ||
        !parse_core(argv[5], &core)) {
        usage(argv[0]);
        return 2;
    }

    alarm(ALARM_SECONDS);
    cpu_set_t requested;
    cpu_set_t observed;
    CPU_ZERO(&requested);
    CPU_SET(core, &requested);
    if (sched_setaffinity(0, sizeof(requested), &requested) != 0 ||
        sched_getaffinity(0, sizeof(observed), &observed) != 0 ||
        CPU_COUNT(&observed) != 1 || !CPU_ISSET(core, &observed)) {
        perror("affinity");
        return 2;
    }

    int input = open(argv[1], O_RDONLY | O_CLOEXEC);
    if (input < 0) {
        perror("open input");
        return 2;
    }
    struct stat input_stat;
    if (fstat(input, &input_stat) != 0 || !S_ISREG(input_stat.st_mode) ||
        input_stat.st_size <= 0 || (uintmax_t)input_stat.st_size > SIZE_MAX) {
        if (errno == 0) {
            errno = EINVAL;
        }
        perror("input geometry");
        close(input);
        return 2;
    }
    size_t input_bytes = (size_t)input_stat.st_size;
    if ((uint64_t)input_bytes > MAX_TOTAL_BYTES / jobs) {
        fprintf(stderr, "total output exceeds 1.5 GB bound\n");
        close(input);
        return 2;
    }

    uint8_t *payload = malloc(input_bytes);
    if (payload == NULL || read_full(input, payload, input_bytes) != 0) {
        perror("read input");
        free(payload);
        close(input);
        return 2;
    }
    if (close(input) != 0) {
        perror("close input");
        free(payload);
        return 2;
    }

    int output = open(argv[2], O_WRONLY | O_CREAT | O_EXCL | O_CLOEXEC, 0640);
    if (output < 0) {
        perror("open output");
        free(payload);
        return 2;
    }

    double epoch_ms = millis(CLOCK_MONOTONIC) + 250.0;
    if (epoch_ms < 0.0 ||
        printf("{\"type\":\"ready\",\"pid\":%ld,\"core\":%d,\"jobs\":%u,"
               "\"period_ms\":%.9g,\"input_bytes\":%zu,\"total_bytes\":%" PRIu64
               ",\"epoch_ms\":%.9f}\n",
               (long)getpid(), core, jobs, period_ms, input_bytes,
               (uint64_t)input_bytes * jobs, epoch_ms) < 0 ||
        fflush(stdout) != 0) {
        perror("write ready record");
        close(output);
        free(payload);
        return 2;
    }

    uint64_t total_bytes = 0;
    for (unsigned job = 0; job < jobs; ++job) {
        double due_ms = epoch_ms + (double)job * period_ms;
        int wait_result = sleep_until(due_ms);
        if (wait_result != 0) {
            errno = wait_result;
            perror("clock_nanosleep");
            close(output);
            free(payload);
            return 2;
        }
        double start_ms = millis(CLOCK_MONOTONIC);
        double cpu_start_ms = millis(CLOCK_PROCESS_CPUTIME_ID);
        if (start_ms < 0.0 || cpu_start_ms < 0.0 ||
            write_full(output, payload, input_bytes) != 0) {
            perror("write output");
            close(output);
            free(payload);
            return 2;
        }
        double end_ms = millis(CLOCK_MONOTONIC);
        double cpu_ms = millis(CLOCK_PROCESS_CPUTIME_ID) - cpu_start_ms;
        if (end_ms < 0.0 || cpu_ms < 0.0) {
            perror("clock_gettime");
            close(output);
            free(payload);
            return 2;
        }
        total_bytes += input_bytes;
        if (printf("{\"type\":\"write\",\"index\":%u,\"due_ms\":%.9f,"
                   "\"start_ms\":%.9f,\"end_ms\":%.9f,\"cpu_ms\":%.9f,"
                   "\"wall_ms\":%.9f,\"queue_ms\":%.9f,\"response_ms\":%.9f,"
                   "\"bytes\":%zu,\"total_bytes\":%" PRIu64 "}\n",
                   job, due_ms, start_ms, end_ms, cpu_ms, end_ms - start_ms,
                   start_ms - due_ms, end_ms - due_ms, input_bytes, total_bytes) < 0 ||
            fflush(stdout) != 0) {
            perror("write visit record");
            close(output);
            free(payload);
            return 2;
        }
    }

    double sync_start_ms = millis(CLOCK_MONOTONIC);
    if (sync_start_ms < 0.0 || fdatasync(output) != 0) {
        perror("fdatasync output");
        close(output);
        free(payload);
        return 2;
    }
    double sync_end_ms = millis(CLOCK_MONOTONIC);
    if (sync_end_ms < 0.0 || close(output) != 0) {
        perror("close output");
        free(payload);
        return 2;
    }
    free(payload);
    if (printf("{\"type\":\"complete\",\"jobs\":%u,\"bytes\":%" PRIu64
               ",\"end_ms\":%.9f,\"sync_wall_ms\":%.9f}\n",
               jobs, total_bytes, sync_end_ms, sync_end_ms - sync_start_ms) < 0 ||
        fflush(stdout) != 0) {
        perror("write complete record");
        return 2;
    }
    return 0;
}
