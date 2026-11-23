/* Add a bounded circular history to the bufferless decoder. */
#include "fused_block_input.c"
#include <string.h>

enum { max_history = 8 * 1024 * 1024 };

typedef struct {
    Member member;
    uint8_t *ring;
    size_t capacity, block, pos, carry_offset, carry;
    uint64_t wraps, copied;
} Ring;

size_t fused_ring_capacity(const uint8_t *data, size_t size, size_t extent, uint64_t geometry[2]) {
    if (fused_frame_supported(data, size, extent)) return 0;
    ZSTD_frameHeader header;
    if (ZSTD_getFrameHeader(&header, data, size) || header.windowSize > max_history ||
        !header.blockSizeMax)
        return 0;
    size_t bytes = ZSTD_decodingBufferSize_min(header.windowSize, header.frameContentSize);
    if (ZSTD_isError(bytes) || bytes > max_history + 3 * ZSTD_BLOCKSIZE_MAX || bytes < header.blockSizeMax)
        return 0;
    geometry[0] = header.windowSize;
    geometry[1] = header.blockSizeMax;
    return bytes;
}

Ring *fused_ring_create(const uint8_t *compressed, size_t compressed_size, size_t extent,
                        size_t capacity, size_t block) {
    if (leo_paired_sha256_context_size() != sizeof(SHA256_CTX)) return NULL;
    Ring *ring = calloc(1, sizeof(*ring));
    if (!ring) return NULL;
    Member *m = &ring->member;
    ring->ring = malloc(capacity);
    m->decoder = ZSTD_createDCtx();
    if (!ring->ring || !m->decoder || ZSTD_isError(ZSTD_decompressBegin(m->decoder)) ||
        !leo_paired_sha256_init(&m->hash)) {
        ZSTD_freeDCtx(m->decoder);
        free(ring->ring);
        free(ring);
        return NULL;
    }
    ring->capacity = capacity;
    ring->block = block;
    m->compressed = compressed;
    m->input_size = compressed_size;
    m->output_size = extent;
    return ring;
}

void fused_ring_free(Ring *ring) {
    if (!ring) return;
    ZSTD_freeDCtx(ring->member.decoder);
    free(ring->ring);
    free(ring);
}

/* No unconsumed bytes may remain when a block wraps to the ring's start.
   Buffer size and the full-block headroom rule preserve Zstd backreferences. */
static int next_block(Ring *ring) {
    Member *m = &ring->member;
    size_t count = ZSTD_nextSrcSizeToDecompress(m->decoder);
    if (!count || count > m->input_size - m->input) return invalid;
    ZSTD_nextInputType_e type = ZSTD_nextInputType(m->decoder);
    if ((type == ZSTDnit_block || type == ZSTDnit_lastBlock) &&
        ring->capacity - ring->pos < ring->block) {
        ring->pos = 0;
        ++ring->wraps;
    }
    size_t bytes = ZSTD_decompressContinue(m->decoder, ring->ring + ring->pos, ring->capacity - ring->pos,
                                           m->compressed + m->input, count);
    if (ZSTD_isError(bytes)) return invalid;
    if (bytes > m->output_size - m->written) return wrong_extent;
    ring->carry = bytes;
    ring->carry_offset = ring->pos;
    ring->pos += bytes;
    m->written += bytes;
    m->input += count;
    ++m->steps;
    return done;
}

int fused_ring_window(Ring *ring, uint8_t *destination, size_t size, uint8_t digest[32]) {
    Member *m = &ring->member;
    if (size > m->output_size - m->verified) return wrong_extent;
    uint64_t start = cpu_ns();
    size_t offset = 0;
    while (offset < size) {
        if (!ring->carry) {
            int status = next_block(ring);
            if (status) return status;
            continue;
        }
        size_t slice = ring->carry < size - offset ? ring->carry : size - offset;
        memcpy(destination + offset, ring->ring + ring->carry_offset, slice);
        ring->carry_offset += slice;
        ring->carry -= slice;
        offset += slice;
    }
    m->decode_cpu_ns += cpu_ns() - start;
    start = cpu_ns();
    if (!leo_paired_sha256_window(&m->hash, destination, size, digest)) return invalid;
    m->hash_cpu_ns += cpu_ns() - start;
    m->verified += size;
    ring->copied += size;
    ++m->windows;
    return done;
}

int fused_ring_end(Ring *ring, uint8_t digest[32], uint64_t stats[6]) {
    Member *m = &ring->member;
    if (m->verified != m->output_size || ring->carry) return wrong_extent;
    uint64_t start = cpu_ns();
    while (ZSTD_nextSrcSizeToDecompress(m->decoder)) {
        int status = next_block(ring);
        if (status) return status;
        if (ring->carry) return wrong_extent;
    }
    if (m->input != m->input_size || m->written != m->output_size) return wrong_extent;
    m->decode_cpu_ns += cpu_ns() - start;
    start = cpu_ns();
    if (!leo_paired_sha256_digest(&m->hash, digest)) return invalid;
    m->hash_cpu_ns += cpu_ns() - start;
    stats[0] = m->decode_cpu_ns;
    stats[1] = m->hash_cpu_ns;
    stats[2] = m->steps;
    stats[3] = m->windows;
    stats[4] = ring->wraps;
    stats[5] = ring->copied;
    return done;
}
