/* Test-only linker clock wrapper. The production SDK always uses the real
 * monotonic clock; its worker is separately exec'd and is never wrapped. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <stdint.h>
#include <time.h>

static uint64_t frozen_ns;
static int frozen, broken;
int __real_clock_gettime(clockid_t, struct timespec *);
void leo_test_clock(uint64_t ns, int mode)
{
    frozen_ns=ns; frozen=mode!=0; broken=mode<0;
}
int __wrap_clock_gettime(clockid_t which, struct timespec *out)
{
    if (!frozen || which!=CLOCK_MONOTONIC) return __real_clock_gettime(which,out);
    if (broken) { errno=EIO; return -1; }
    out->tv_sec=(time_t)(frozen_ns/1000000000);
    out->tv_nsec=(long)(frozen_ns%1000000000);
    return 0;
}
