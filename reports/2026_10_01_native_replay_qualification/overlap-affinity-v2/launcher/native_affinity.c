#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

/* Narrow two-core diagnostic launcher. Inherited by exec and child threads. */
int main(int argc, char **argv) {
    if (argc < 3 || strlen(argv[1]) != 1 || argv[1][0] < '1' || argv[1][0] > '3') {
        fprintf(stderr, "usage: native-affinity {1|2|3} command [args...]\n");
        return 2;
    }
    unsigned mask = (unsigned)(argv[1][0] - '0');
    cpu_set_t requested, actual;
    CPU_ZERO(&requested);
    for (unsigned cpu = 0; cpu < 2; ++cpu)
        if (mask & (1u << cpu)) CPU_SET(cpu, &requested);
    if (sched_setaffinity(0, sizeof(requested), &requested) ||
        sched_getaffinity(0, sizeof(actual), &actual)) {
        perror("affinity");
        return 3;
    }
    if (!CPU_EQUAL(&requested, &actual)) {
        fprintf(stderr, "requested CPUs unavailable\n");
        return 3;
    }
    execvp(argv[2], argv + 2);
    perror("exec");
    return 127;
}
