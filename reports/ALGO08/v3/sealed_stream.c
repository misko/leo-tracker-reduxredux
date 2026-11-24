#define _POSIX_C_SOURCE 200809L
#define ZSTD_STATIC_LINKING_ONLY
#include <errno.h>
#include <openssl/sha.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <zstd.h>

int leo_paired_sha256_init(SHA256_CTX *);
int leo_paired_sha256_window(SHA256_CTX *, const uint8_t *, size_t, uint8_t *);
int leo_paired_sha256_digest(const SHA256_CTX *, uint8_t *);
size_t leo_paired_sha256_context_size(void);

enum {
    member_limit = 128 * 1024 * 1024, history_limit = 8 * 1024 * 1024,
    read_size = 256 * 1024, window_limit = 1600000
};
enum {
    verified, unsupported, bad_descriptor, bad_frame, bad_extent,
    bad_compressed_digest, bad_window_digest, bad_member_digest, setup_failed
};

typedef struct {
    size_t size;
    uint8_t expected[SHA256_DIGEST_LENGTH], actual[SHA256_DIGEST_LENGTH];
} Window;

typedef struct {
    uint64_t read_cpu_ns, compressed_hash_cpu_ns, decode_cpu_ns, window_hash_cpu_ns,
             reads, compressed_bytes, decoded_bytes, windows, history_bytes;
} Stats;

static uint64_t cpu_ns(void)
{
    struct timespec tick;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &tick)) return 0;
    return (uint64_t)tick.tv_sec * UINT64_C(1000000000) + (uint64_t)tick.tv_nsec;
}

static ssize_t read_retry(int fd, void *bytes, size_t size)
{
    ssize_t got;
    do {
        got = read(fd, bytes, size);
    } while (got < 0 && errno == EINTR);
    return got;
}

static int regular(const struct stat *file, size_t size)
{
    return S_ISREG(file->st_mode) && file->st_nlink == 1 && file->st_size >= 0 &&
           (uintmax_t)file->st_size == size;
}

static int same_descriptor(const struct stat *before, const struct stat *after, size_t size)
{
    return regular(after, size) && before->st_dev == after->st_dev && before->st_ino == after->st_ino &&
           before->st_mtim.tv_sec == after->st_mtim.tv_sec &&
           before->st_mtim.tv_nsec == after->st_mtim.tv_nsec;
}

static int decode(int fd, size_t compressed_size, const uint8_t *compressed_sha,
                  uint8_t *scratch, ZSTD_DCtx *decoder, ZSTD_outBuffer *output,
                  Window *rows, size_t row_count, uint8_t *member_sha, Stats *stats)
{
    SHA256_CTX compressed, member;
    if (!SHA256_Init(&compressed) || !leo_paired_sha256_init(&member)) return setup_failed;
    size_t remaining = 1, accounted = 0, pending = 0;
    while (stats->compressed_bytes < compressed_size) {
        size_t wanted = compressed_size - stats->compressed_bytes;
        if (wanted > read_size) wanted = read_size;
        uint64_t started = cpu_ns();
        size_t obtained = 0;
        while (obtained < wanted) {
            const ssize_t got = read_retry(fd, scratch + obtained, wanted - obtained);
            if (got <= 0) return bad_descriptor;
            obtained += (size_t)got;
            ++stats->reads;
        }
        stats->read_cpu_ns += cpu_ns() - started;
        if (!stats->compressed_bytes) {
            ZSTD_frameHeader header;
            if (ZSTD_getFrameHeader(&header, scratch, obtained)) return bad_frame;
            if (header.frameType != ZSTD_frame || header.dictID || !header.checksumFlag ||
                header.windowSize > history_limit)
                return unsupported;
            if (header.frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN && header.frameContentSize != output->size)
                return unsupported;
            stats->history_bytes = header.windowSize;
        }
        stats->compressed_bytes += obtained;
        started = cpu_ns();
        if (!SHA256_Update(&compressed, scratch, obtained)) return setup_failed;
        stats->compressed_hash_cpu_ns += cpu_ns() - started;
        ZSTD_inBuffer input = {scratch, obtained, 0};
        while (input.pos < input.size) {
            size_t prior_in = input.pos, prior_out = output->pos;
            started = cpu_ns();
            remaining = ZSTD_decompressStream(decoder, output, &input);
            stats->decode_cpu_ns += cpu_ns() - started;
            if (ZSTD_isError(remaining)) return bad_frame;
            if (!remaining && (input.pos != input.size || stats->compressed_bytes != compressed_size))
                return unsupported;
            if (prior_in == input.pos && prior_out == output->pos) return bad_extent;
            while (pending < row_count && rows[pending].size <= output->pos - accounted) {
                Window *row = rows + pending;
                started = cpu_ns();
                if (!leo_paired_sha256_window(&member, (const uint8_t *)output->dst + accounted,
                                              row->size, row->actual))
                    return setup_failed;
                stats->window_hash_cpu_ns += cpu_ns() - started;
                accounted += row->size;
                ++pending;
            }
        }
    }
    uint8_t extra, actual[SHA256_DIGEST_LENGTH];
    if (read_retry(fd, &extra, 1) != 0) return bad_descriptor;
    if (remaining || output->pos != output->size || accounted != output->size || pending != row_count)
        return bad_extent;
    stats->decoded_bytes = output->pos;
    stats->windows = pending;
    uint64_t started = cpu_ns();
    if (!SHA256_Final(actual, &compressed)) return setup_failed;
    stats->compressed_hash_cpu_ns += cpu_ns() - started;
    if (memcmp(actual, compressed_sha, sizeof(actual))) return bad_compressed_digest;
    for (size_t i = 0; i < row_count; ++i) {
        if (memcmp(rows[i].expected, rows[i].actual, sizeof(rows[i].actual))) return bad_window_digest;
    }
    started = cpu_ns();
    if (!leo_paired_sha256_digest(&member, member_sha)) return setup_failed;
    stats->window_hash_cpu_ns += cpu_ns() - started;
    return verified;
}

int sealed_stream_decode(int fd, size_t compressed_size, const uint8_t *compressed_sha,
                         void *output_bytes, size_t output_size, Window *rows, size_t row_count,
                         const uint8_t *expected_member_sha, uint8_t *member_sha, Stats *stats)
{
    if (!compressed_size || compressed_size > member_limit || !output_size || output_size > member_limit ||
        !row_count || !rows || !compressed_sha || !expected_member_sha || !member_sha || !output_bytes || !stats)
        return unsupported;
    *stats = (Stats){0};
    size_t total = 0;
    for (size_t i = 0; i < row_count; ++i) {
        if (!rows[i].size || rows[i].size > window_limit || rows[i].size > output_size - total)
            return unsupported;
        total += rows[i].size;
    }
    if (total != output_size) return unsupported;
    struct stat before, after;
    if (fstat(fd, &before) || !regular(&before, compressed_size)) return bad_descriptor;
    if (leo_paired_sha256_context_size() != sizeof(SHA256_CTX)) return setup_failed;
    uint8_t *scratch = malloc(read_size);
    ZSTD_DCtx *decoder = ZSTD_createDCtx();
    int status = setup_failed;
    if (scratch && decoder &&
        !ZSTD_isError(ZSTD_DCtx_setMaxWindowSize(decoder, history_limit)) &&
        !ZSTD_isError(ZSTD_DCtx_setParameter(decoder, ZSTD_d_stableOutBuffer, 1))) {
        ZSTD_outBuffer output = {output_bytes, output_size, 0};
        status = decode(fd, compressed_size, compressed_sha, scratch, decoder, &output, rows, row_count,
                        member_sha, stats);
        if (status == verified) {
            if (fstat(fd, &after) || !same_descriptor(&before, &after, compressed_size))
                status = bad_descriptor;
            else if (memcmp(member_sha, expected_member_sha, SHA256_DIGEST_LENGTH))
                status = bad_member_digest;
        }
    }
    ZSTD_freeDCtx(decoder);
    free(scratch);
    return status;
}
