#define _GNU_SOURCE
#include <errno.h>
#include <stdint.h>
#include <sys/syscall.h>
#include <unistd.h>

#ifdef SYS_cachestat
#include <linux/mman.h>
#endif

/* Query existing cache entries without reading, mapping or advising file data. */
int leo_cached_pages(int fd, uint64_t length, uint64_t *pages)
{
#ifdef SYS_cachestat
    struct cachestat_range range = { .off = 0, .len = length };
    struct cachestat info;
    if (syscall(SYS_cachestat, fd, &range, &info, 0) != 0)
        return errno;
    *pages = info.nr_cache;
    return 0;
#else
    (void)fd;
    (void)length;
    (void)pages;
    return ENOSYS;
#endif
}
