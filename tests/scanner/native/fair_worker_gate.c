/* Test-only publication gate for the actual numerical worker. The parent
 * controls virtual completion time using STOP/CONT, without replacing scores,
 * pool ownership, source bindings or the real worker's lifecycle. */
#define _POSIX_C_SOURCE 200809L
#include "pool.h"
#include <signal.h>

int __real_leo_probe_complete(leo_probe_pool *, uint32_t, const leo_probe_result *);
int __wrap_leo_probe_complete(leo_probe_pool *pool, uint32_t slot,
    const leo_probe_result *result)
{
    if (raise(SIGSTOP)) return -1; /* Computed, but still owns WORKING IQ. */
    int status=__real_leo_probe_complete(pool,slot,result);
    if (raise(SIGSTOP)) return -1; /* Publication is now complete. */
    return status;
}
