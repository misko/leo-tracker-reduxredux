#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

/* Test-process workaround for the exhausted shared /tmp user quota. */
FILE *tmpfile(void) {
    const char *directory=getenv("LEO_TEST_TMPDIR");
    if (!directory || !*directory) {
        errno=EINVAL;
        return NULL;
    }
    const char suffix[]="/tmpfile.XXXXXX";
    const size_t size=strlen(directory)+sizeof(suffix);
    char *path=malloc(size);
    if (!path) return NULL;
    if (snprintf(path,size,"%s%s",directory,suffix)<0) {
        free(path);
        errno=EINVAL;
        return NULL;
    }
    const int descriptor=mkstemp(path);
    if (descriptor<0) {
        free(path);
        return NULL;
    }
    if (unlink(path)) {
        const int error=errno;
        close(descriptor);
        free(path);
        errno=error;
        return NULL;
    }
    free(path);
    FILE *stream=fdopen(descriptor,"w+b");
    if (!stream) {
        const int error=errno;
        close(descriptor);
        errno=error;
    }
    return stream;
}
