#define _POSIX_C_SOURCE 200809L
#define ZSTD_STATIC_LINKING_ONLY
#include <openssl/sha.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <zstd.h>

size_t leo_paired_sha256_context_size(void);
int leo_paired_sha256_init(SHA256_CTX *);
int leo_paired_sha256_window(SHA256_CTX *, const uint8_t *, size_t, uint8_t *);
int leo_paired_sha256_digest(const SHA256_CTX *, uint8_t *);

enum { max_member = 128 * 1024 * 1024, scratch_bytes = 1600000 };
enum {
    ok, unsupported, wrong_geometry, malformed_frame, wrong_window_digest, wrong_member_digest
};

typedef struct {
    size_t size;
    uint8_t digest[SHA256_DIGEST_LENGTH];
} SignedWindow;

typedef struct {
    uint64_t decode_cpu_ns, hash_cpu_ns, decoded_bytes;
    uint64_t frame_header_bytes, history_bytes, block_bytes, content_size, checksum, windows;
} DrainStats;

typedef struct {
    ZSTD_DCtx *decoder;
    uint8_t scratch[scratch_bytes];
} Drain;

static uint64_t cpu_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now)) return 0;
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

Drain *verified_drain_create(void) {
    if (sizeof(SHA256_CTX) != leo_paired_sha256_context_size()) return NULL;
    Drain *work = malloc(sizeof(*work));
    if (!work) return NULL;
    work->decoder = ZSTD_createDCtx();
    if (!work->decoder) {
        free(work);
        return NULL;
    }
    return work;
}

void verified_drain_free(Drain *work) {
    if (!work) return;
    ZSTD_freeDCtx(work->decoder);
    free(work);
}

int verified_drain_member(Drain *work, const uint8_t *compressed, size_t compressed_size,
                          const SignedWindow *rows, size_t count, size_t decoded_size,
                          const uint8_t expected[SHA256_DIGEST_LENGTH], DrainStats *stats) {
    if (!work || !compressed || !rows || !count || !expected || !stats ||
        !compressed_size || compressed_size > max_member || !decoded_size || decoded_size > max_member)
        return wrong_geometry;
    *stats = (DrainStats){0};
    uint64_t started = cpu_ns();
    ZSTD_frameHeader header;
    const size_t inspected = ZSTD_getFrameHeader(&header, compressed, compressed_size);
    if (inspected) return malformed_frame;
    if (header.frameType != ZSTD_frame || header.dictID || header.windowSize > max_member)
        return unsupported;
    if (header.frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN && header.frameContentSize != decoded_size)
        return wrong_geometry;
    const size_t frame_size = ZSTD_findFrameCompressedSize(compressed, compressed_size);
    if (ZSTD_isError(frame_size)) return malformed_frame;
    if (frame_size != compressed_size) return unsupported;
    if (ZSTD_isError(ZSTD_DCtx_reset(work->decoder, ZSTD_reset_session_only))) return malformed_frame;
    stats->frame_header_bytes = header.headerSize;
    stats->history_bytes = header.windowSize;
    stats->block_bytes = header.blockSizeMax;
    stats->content_size = header.frameContentSize;
    stats->checksum = header.checksumFlag;
    stats->decode_cpu_ns = cpu_ns() - started;

    ZSTD_inBuffer input = {compressed, compressed_size, 0};
    SHA256_CTX member;
    if (!leo_paired_sha256_init(&member)) return wrong_member_digest;
    size_t remaining = 1;
    for (size_t i = 0; i < count; ++i) {
        const size_t size = rows[i].size;
        if (!size || size > sizeof(work->scratch) || size > decoded_size - stats->decoded_bytes)
            return wrong_geometry;
        started = cpu_ns();
        ZSTD_outBuffer output = {work->scratch, size, 0};
        while (output.pos < size) {
            if (!remaining) return wrong_geometry;
            const size_t in_before = input.pos, out_before = output.pos;
            remaining = ZSTD_decompressStream(work->decoder, &output, &input);
            if (ZSTD_isError(remaining)) return malformed_frame;
            if (in_before == input.pos && out_before == output.pos) return wrong_geometry;
        }
        stats->decode_cpu_ns += cpu_ns() - started;

        started = cpu_ns();
        uint8_t digest[SHA256_DIGEST_LENGTH];
        if (!leo_paired_sha256_window(&member, work->scratch, size, digest) ||
            memcmp(digest, rows[i].digest, sizeof(digest)))
            return wrong_window_digest;
        stats->hash_cpu_ns += cpu_ns() - started;
        stats->decoded_bytes += size;
        ++stats->windows;
    }
    if (stats->decoded_bytes != decoded_size) return wrong_geometry;
    started = cpu_ns();
    while (remaining) {
        const size_t previous = input.pos;
        ZSTD_outBuffer tail = {work->scratch, 1, 0};
        remaining = ZSTD_decompressStream(work->decoder, &tail, &input);
        if (ZSTD_isError(remaining)) return malformed_frame;
        if (tail.pos || (remaining && input.pos == previous)) return wrong_geometry;
    }
    if (input.pos != compressed_size) return wrong_geometry;
    stats->decode_cpu_ns += cpu_ns() - started;
    started = cpu_ns();
    uint8_t digest[SHA256_DIGEST_LENGTH];
    if (!leo_paired_sha256_digest(&member, digest) || memcmp(digest, expected, sizeof(digest)))
        return wrong_member_digest;
    stats->hash_cpu_ns += cpu_ns() - started;
    return ok;
}
