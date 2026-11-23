/* Research-only bufferless Zstandard stream with window and full-member SHA. */
#define _POSIX_C_SOURCE 200809L
#define ZSTD_STATIC_LINKING_ONLY
#include <openssl/sha.h>
#include <stdint.h>
#include <stdlib.h>
#include <time.h>
#include <zstd.h>

size_t leo_paired_sha256_context_size(void);
int leo_paired_sha256_init(SHA256_CTX *);
int leo_paired_sha256_window(SHA256_CTX *, const uint8_t *, size_t, uint8_t *);
int leo_paired_sha256_digest(const SHA256_CTX *, uint8_t *);

enum { max_size = 128 * 1024 * 1024 };
enum { done, unsupported, invalid, wrong_extent };

typedef struct {
    ZSTD_DCtx *decoder;
    const uint8_t *compressed;
    uint8_t *output;
    size_t input_size, output_size, input, written, verified;
    SHA256_CTX hash;
    uint64_t decode_cpu_ns, hash_cpu_ns, steps, windows;
} Member;

static uint64_t cpu_ns(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now)) return 0;
    return (uint64_t)now.tv_sec * UINT64_C(1000000000) + (uint64_t)now.tv_nsec;
}

int fused_frame_supported(const uint8_t *data, size_t size, size_t extent) {
    if (!size || !extent || size > max_size || extent > max_size)
        return unsupported;
    ZSTD_frameHeader header;
    if (ZSTD_getFrameHeader(&header, data, size) || header.frameType != ZSTD_frame ||
        header.dictID || header.windowSize > max_size ||
        (header.frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN && header.frameContentSize != extent) ||
        ZSTD_findFrameCompressedSize(data, size) != size)
        return unsupported;
    return done;
}

Member *fused_member_create(const uint8_t *compressed, size_t compressed_size,
                           uint8_t *output, size_t output_size) {
    if (leo_paired_sha256_context_size() != sizeof(SHA256_CTX)) return NULL;
    Member *member = calloc(1, sizeof(*member));
    if (!member) return NULL;
    member->decoder = ZSTD_createDCtx();
    if (!member->decoder || ZSTD_isError(ZSTD_decompressBegin(member->decoder)) ||
        !leo_paired_sha256_init(&member->hash)) {
        ZSTD_freeDCtx(member->decoder);
        free(member);
        return NULL;
    }
    member->compressed = compressed;
    member->output = output;
    member->input_size = compressed_size;
    member->output_size = output_size;
    return member;
}

void fused_member_free(Member *member) {
    if (!member) return;
    ZSTD_freeDCtx(member->decoder);
    free(member);
}

/* Every block is written immediately after the previous block. That invariant
   preserves all decoder history and avoids the stream reader's output copy. */
static int advance(Member *member, size_t limit) {
    uint64_t start = cpu_ns();
    while (member->written < limit || member->verified == member->output_size) {
        size_t count = ZSTD_nextSrcSizeToDecompress(member->decoder);
        if (!count) break;
        if (count > member->input_size - member->input) return invalid;
        size_t available = member->output_size - member->written;
        size_t written = ZSTD_decompressContinue(member->decoder, member->output + member->written,
                                                 available, member->compressed + member->input, count);
        if (ZSTD_isError(written)) return invalid;
        if (written > available) return wrong_extent;
        member->input += count;
        member->written += written;
        ++member->steps;
    }
    member->decode_cpu_ns += cpu_ns() - start;
    return member->written < limit ? wrong_extent : done;
}

int fused_member_window(Member *member, size_t size, uint8_t digest[SHA256_DIGEST_LENGTH]) {
    if (size > member->output_size - member->verified) return wrong_extent;
    int status = advance(member, member->verified + size);
    if (status) return status;
    uint64_t start = cpu_ns();
    if (!leo_paired_sha256_window(&member->hash, member->output + member->verified, size, digest))
        return invalid;
    member->hash_cpu_ns += cpu_ns() - start;
    member->verified += size;
    ++member->windows;
    return done;
}

int fused_member_end(Member *member, uint8_t digest[SHA256_DIGEST_LENGTH], uint64_t stats[4]) {
    if (member->verified != member->output_size) return wrong_extent;
    int status = advance(member, member->output_size);
    if (status) return status;
    if (member->input != member->input_size || member->written != member->output_size)
        return wrong_extent;
    uint64_t start = cpu_ns();
    if (!leo_paired_sha256_digest(&member->hash, digest)) return invalid;
    member->hash_cpu_ns += cpu_ns() - start;
    stats[0] = member->decode_cpu_ns;
    stats[1] = member->hash_cpu_ns;
    stats[2] = member->steps;
    stats[3] = member->windows;
    return done;
}
