/* Read-only per-core and per-process CPU accounting sampler for saved-IQ runs. */
#define _POSIX_C_SOURCE 200809L

#include <ctype.h>
#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

enum { MAX_CORES = 256, MAX_PIDS = 64, STAT_FIELDS = 10 };

typedef struct {
    unsigned long long value[STAT_FIELDS];
} CpuCounters;

typedef struct {
    int cpu;
    CpuCounters counters;
} CoreSample;

typedef struct {
    bool present;
    unsigned long long utime;
    unsigned long long stime;
} ProcessSample;

static const char *field_names[STAT_FIELDS] = {
    "user", "nice", "system", "idle", "iowait", "irq", "softirq", "steal",
    "guest", "guest_nice"
};

static long long monotonic_ms(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) != 0) {
        return -1;
    }
    return (long long)now.tv_sec * 1000LL + now.tv_nsec / 1000000L;
}

static int read_cores(const char *proc_root, CoreSample *cores, size_t *count) {
    char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/stat", proc_root) >= (int)sizeof(path)) {
        return -1;
    }
    FILE *stream = fopen(path, "r");
    if (stream == NULL) {
        return -1;
    }
    char line[1024];
    size_t found = 0;
    while (fgets(line, sizeof(line), stream) != NULL) {
        int cpu = -1;
        char name[32];
        if (sscanf(line, "%31s", name) != 1 ||
            sscanf(name, "cpu%d", &cpu) != 1 || cpu < 0) {
            continue;
        }
        if (found == MAX_CORES) {
            fclose(stream);
            errno = E2BIG;
            return -1;
        }
        char *cursor = line + strlen(name);
        CoreSample sample = {.cpu = cpu};
        for (size_t i = 0; i < STAT_FIELDS; ++i) {
            errno = 0;
            while (isspace((unsigned char)*cursor)) {
                ++cursor;
            }
            if (*cursor == '\0' || *cursor == '\n') {
                break;
            }
            char *end = NULL;
            sample.counters.value[i] = strtoull(cursor, &end, 10);
            if (errno != 0 || end == cursor) {
                fclose(stream);
                return -1;
            }
            cursor = end;
        }
        cores[found++] = sample;
    }
    fclose(stream);
    *count = found;
    return found == 0 ? -1 : 0;
}

/* Linux /proc/PID/stat has a parenthesized comm which may itself contain spaces
 * and ')' characters.  The final ')' is the only reliable field-three boundary. */
static ProcessSample read_process(const char *proc_root, pid_t pid) {
    ProcessSample result = {0};
    char path[PATH_MAX];
    if (snprintf(path, sizeof(path), "%s/%ld/stat", proc_root, (long)pid) >=
        (int)sizeof(path)) {
        return result;
    }
    FILE *stream = fopen(path, "r");
    if (stream == NULL) {
        return result;
    }
    char line[4096];
    if (fgets(line, sizeof(line), stream) == NULL) {
        fclose(stream);
        return result;
    }
    fclose(stream);
    char *close = strrchr(line, ')');
    if (close == NULL) {
        return result;
    }
    char *cursor = close + 1;
    while (isspace((unsigned char)*cursor)) {
        ++cursor;
    }
    if (*cursor == '\0') {
        return result;
    }
    ++cursor; /* state (field 3) */
    for (int number = 1; number <= 12; ++number) {
        while (isspace((unsigned char)*cursor)) {
            ++cursor;
        }
        errno = 0;
        char *end = NULL;
        unsigned long long value = strtoull(cursor, &end, 10);
        if (errno != 0 || end == cursor) {
            return result;
        }
        if (number == 11) {
            result.utime = value; /* field 14 */
        } else if (number == 12) {
            result.stime = value; /* field 15 */
        }
        cursor = end;
    }
    result.present = true;
    return result;
}

static unsigned long long delta(unsigned long long before, unsigned long long after) {
    return after >= before ? after - before : 0;
}

static const CoreSample *find_core(const CoreSample *cores, size_t count, int cpu) {
    for (size_t i = 0; i < count; ++i) {
        if (cores[i].cpu == cpu) {
            return &cores[i];
        }
    }
    return NULL;
}

static void print_counters(const CpuCounters *current, const CpuCounters *previous) {
    putchar('{');
    for (size_t i = 0; i < STAT_FIELDS; ++i) {
        printf("\"%s\":%llu%s", field_names[i], current->value[i],
               i + 1 == STAT_FIELDS ? "" : ",");
    }
    fputs("},\"delta\":", stdout);
    if (previous == NULL) {
        fputs("null", stdout);
        return;
    }
    putchar('{');
    for (size_t i = 0; i < STAT_FIELDS; ++i) {
        printf("\"%s\":%llu%s", field_names[i],
               delta(previous->value[i], current->value[i]),
               i + 1 == STAT_FIELDS ? "" : ",");
    }
    putchar('}');
}

static void print_process(pid_t pid, ProcessSample current, const ProcessSample *previous) {
    printf("{\"pid\":%ld,\"present\":%s", (long)pid,
           current.present ? "true" : "false");
    if (!current.present) {
        fputs("}", stdout);
        return;
    }
    printf(",\"utime_ticks\":%llu,\"stime_ticks\":%llu,\"delta\":",
           current.utime, current.stime);
    if (previous == NULL || !previous->present) {
        fputs("null", stdout);
    } else {
        printf("{\"utime_ticks\":%llu,\"stime_ticks\":%llu}",
               delta(previous->utime, current.utime), delta(previous->stime, current.stime));
    }
    putchar('}');
}

static void usage(const char *name) {
    fprintf(stderr, "usage: %s [--proc-root PATH] DURATION_SECONDS [PID ...]\\n", name);
}

int main(int argc, char **argv) {
    const char *proc_root = "/proc";
    int argument = 1;
    if (argument + 1 < argc && strcmp(argv[argument], "--proc-root") == 0) {
        proc_root = argv[argument + 1];
        argument += 2;
    }
    if (argument >= argc) {
        usage(argv[0]);
        return 2;
    }
    char *end = NULL;
    errno = 0;
    long duration = strtol(argv[argument++], &end, 10);
    if (errno != 0 || end == argv[argument - 1] || *end != '\0' || duration < 1 || duration > 180) {
        usage(argv[0]);
        return 2;
    }
    if (argc - argument > MAX_PIDS) {
        fprintf(stderr, "too many PIDs (maximum %d)\\n", MAX_PIDS);
        return 2;
    }
    pid_t pids[MAX_PIDS];
    size_t pid_count = 0;
    for (; argument < argc; ++argument) {
        errno = 0;
        long value = strtol(argv[argument], &end, 10);
        if (errno != 0 || end == argv[argument] || *end != '\0' || value <= 0 || value > INT_MAX) {
            usage(argv[0]);
            return 2;
        }
        pids[pid_count++] = (pid_t)value;
    }

    CoreSample previous_cores[MAX_CORES];
    size_t previous_count = 0;
    ProcessSample previous_processes[MAX_PIDS] = {{0}};
    ProcessSample previous_self = {0};
    long long started = monotonic_ms();
    if (started < 0) {
        perror("clock_gettime");
        return 1;
    }
    for (long sample = 0; sample <= duration; ++sample) {
        if (sample != 0) {
            struct timespec target = {.tv_sec = started / 1000 + sample,
                                      .tv_nsec = (started % 1000) * 1000000L};
            int wait_result;
            do {
                wait_result = clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &target, NULL);
            } while (wait_result == EINTR);
            if (wait_result != 0) {
                errno = wait_result;
                perror("clock_nanosleep");
                return 1;
            }
        }
        CoreSample current_cores[MAX_CORES];
        size_t current_count = 0;
        if (read_cores(proc_root, current_cores, &current_count) != 0) {
            perror("read /proc/stat");
            return 1;
        }
        ProcessSample current_processes[MAX_PIDS] = {{0}};
        for (size_t i = 0; i < pid_count; ++i) {
            current_processes[i] = read_process(proc_root, pids[i]);
        }
        ProcessSample current_self = read_process(proc_root, getpid());
        long long now = monotonic_ms();
        if (now < 0) {
            perror("clock_gettime");
            return 1;
        }
        printf("{\"schema\":\"org.leo.research.cpu-monitor/v1\",\"type\":\"sample\","
               "\"sample\":%ld,\"monotonic_ms\":%lld,\"cores\":[", sample, now);
        for (size_t i = 0; i < current_count; ++i) {
            const CoreSample *old = find_core(previous_cores, previous_count, current_cores[i].cpu);
            printf("{\"cpu\":%d,\"raw\":", current_cores[i].cpu);
            print_counters(&current_cores[i].counters, old == NULL ? NULL : &old->counters);
            fputs("}", stdout);
            if (i + 1 != current_count) {
                putchar(',');
            }
        }
        fputs("],\"processes\":[", stdout);
        for (size_t i = 0; i < pid_count; ++i) {
            print_process(pids[i], current_processes[i], sample == 0 ? NULL : &previous_processes[i]);
            if (i + 1 != pid_count) {
                putchar(',');
            }
        }
        fputs("],\"self\":", stdout);
        print_process(getpid(), current_self, sample == 0 ? NULL : &previous_self);
        fputs("}\n", stdout);
        fflush(stdout);
        memcpy(previous_cores, current_cores, current_count * sizeof(*current_cores));
        previous_count = current_count;
        memcpy(previous_processes, current_processes, pid_count * sizeof(*current_processes));
        previous_self = current_self;
    }
    return 0;
}
