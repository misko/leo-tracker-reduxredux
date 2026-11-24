/* Exact whole-frame decode with bounded libzstd history and optional block capture. */
#define ZSTD_STATIC_LINKING_ONLY
#include <zstd.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { BLOCK_MAX = 128 * 1024, WINDOW_LIMIT = 8 * 1024 * 1024 };

typedef struct {
    uint32_t encoded, length, origin, literals, sequences;
} description;

typedef struct {
    uint32_t encoded, length, decoded, count, origin;
} block;

typedef struct {
    ZSTD_DCtx *zstd;
    const unsigned char *source;
    const description *plan;
    block *result;
    unsigned char *escapes;
    size_t encoded, expected, nblocks, exceptions;
    size_t consumed, decoded, nth, retained, checksums;
    size_t ring_size, write_at, max_block, pending, owned;
    const unsigned char *pending_data;
    unsigned char *output_end;
    int failed;
    unsigned char ring[];
} history;

history *fused_history_open_owned(const unsigned char *source, size_t encoded, size_t expected,
                                 const description *plan, size_t nblocks, block *result,
                                 unsigned char *escapes, size_t exceptions, size_t owned)
{
    ZSTD_FrameHeader header;
    if (ZSTD_getFrameHeader(&header, source, encoded) || header.frameType != ZSTD_frame ||
        header.dictID || !header.checksumFlag || !header.windowSize ||
        header.windowSize > WINDOW_LIMIT || !header.blockSizeMax || header.blockSizeMax > BLOCK_MAX ||
        !expected || expected > UINT32_MAX || encoded > UINT32_MAX ||
        (header.frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN && header.frameContentSize != expected))
        return NULL;
    if (!plan && ZSTD_findFrameCompressedSize(source, encoded) != encoded) return NULL;
    /* There can be up to one copied block tail before the first direct block
       in a window. Even then the contiguous prefix must hold the full history
       when libzstd crosses to a new destination. */
    if (owned < header.windowSize + header.blockSizeMax || expected % owned) owned = 0;
    size_t ring_size = 0;
    if (!owned) {
        ring_size = ZSTD_decodingBufferSize_min(header.windowSize, header.frameContentSize);
        if (ZSTD_isError(ring_size) || !ring_size || ring_size > WINDOW_LIMIT + 4 * BLOCK_MAX) return NULL;
    }
    history *state = calloc(1, sizeof(*state) + ring_size);
    if (!state) return NULL;
    state->zstd = ZSTD_createDCtx();
    if (!state->zstd || ZSTD_isError(ZSTD_decompressBegin(state->zstd))) {
        ZSTD_freeDCtx(state->zstd);
        free(state);
        return NULL;
    }
    state->source = source;
    state->encoded = encoded;
    state->expected = expected;
    state->plan = plan;
    state->nblocks = nblocks;
    state->result = result;
    state->escapes = escapes;
    state->exceptions = exceptions;
    state->ring_size = ring_size;
    state->max_block = header.blockSizeMax;
    state->owned = owned;
    return state;
}

history *fused_history_open(const unsigned char *source, size_t encoded, size_t expected,
                            const description *plan, size_t nblocks, block *result,
                            unsigned char *escapes, size_t exceptions)
{
    return fused_history_open_owned(source, encoded, expected, plan, nblocks, result, escapes, exceptions, 0);
}

history *fused_history_open_unindexed(const unsigned char *source, size_t encoded, size_t expected, size_t owned)
{
    return fused_history_open_owned(source, encoded, expected, NULL, 0, NULL, NULL, 0, owned);
}

void fused_history_close(history *state)
{
    ZSTD_freeDCtx(state->zstd);
    free(state);
}

size_t fused_history_scratch(const history *state)
{
    return sizeof(*state) + state->ring_size + ZSTD_sizeof_DCtx(state->zstd);
}

/* Return 1 after one verified decoded block, 0 at native EOF, -1 on failure. */
static int next_block(history *state, unsigned char *destination, size_t capacity)
{
    size_t bytes;
    while ((bytes = ZSTD_nextSrcSizeToDecompress(state->zstd))) {
        if (bytes > state->encoded - state->consumed) return -1;
        ZSTD_nextInputType_e kind = ZSTD_nextInputType(state->zstd);
        int data = kind == ZSTDnit_block || kind == ZSTDnit_lastBlock;
        if (!data && kind != ZSTDnit_frameHeader && kind != ZSTDnit_blockHeader &&
            kind != ZSTDnit_checksum) return -1;
        if (data && !destination) {
            size_t remaining = state->expected - state->decoded;
            size_t extent = remaining < state->max_block ? remaining : state->max_block;
            if (state->ring_size - state->write_at < extent) state->write_at = 0;
        }
        unsigned char *output = destination ? destination : state->ring + state->write_at;
        size_t available = destination ? capacity : state->ring_size - state->write_at;
        size_t count = ZSTD_decompressContinue(state->zstd, output, available,
                                               state->source + state->consumed, bytes);
        if (ZSTD_isError(count) || count > state->expected - state->decoded) return -1;
        size_t encoded_at = state->consumed;
        state->consumed += bytes;
        if (kind == ZSTDnit_checksum) state->checksums++;
        if (!data) {
            if (count) return -1;
            continue;
        }
        if (count > state->max_block) return -1;
        if (state->plan) {
            if (state->nth >= state->nblocks || !count) return -1;
            const description *entry = state->plan + state->nth;
            if (entry->encoded != encoded_at || entry->length != bytes || entry->origin > state->nth ||
                (entry->sequences ? (uint64_t)entry->literals + (uint64_t)3 * entry->sequences > count
                                  : entry->literals != count)) return -1;
            state->result[state->nth++] = (block){entry->encoded, entry->length, (uint32_t)state->decoded,
                                                  (uint32_t)count, entry->origin};
            if (entry->sequences) {
                if (state->retained >= state->exceptions) return -1;
                memcpy(state->escapes + state->retained++ * BLOCK_MAX, output, count);
            }
        }
        if (!count) continue;
        state->pending_data = output;
        state->pending = count;
        if (destination) state->output_end = output + count;
        else state->write_at += count;
        state->decoded += count;
        return 1;
    }
    return 0;
}

int fused_history_read(history *state, unsigned char *destination, size_t bytes)
{
    if (state->owned) return 0;
    while (!state->failed && bytes) {
        if (!state->pending && next_block(state, NULL, 0) != 1) {
            state->failed = 1;
            break;
        }
        size_t copy = bytes < state->pending ? bytes : state->pending;
        memcpy(destination, state->pending_data, copy);
        state->pending_data += copy;
        state->pending -= copy;
        destination += copy;
        bytes -= copy;
    }
    return !state->failed;
}

size_t fused_history_owned_capacity(const history *state)
{
    return state->owned ? state->owned + state->max_block : 0;
}

/* Each buffer is owned by its caller. The previous buffer must stay live
   throughout this call, so libzstd can refer to its external dictionary. */
int fused_history_read_owned(history *state, unsigned char *destination, size_t capacity)
{
    if (state->failed || !state->owned || capacity < fused_history_owned_capacity(state)) return 0;
    size_t filled = state->pending;
    if (filled) memcpy(destination, state->pending_data, filled);
    state->pending = 0;
    while (filled < state->owned) {
        if (next_block(state, destination + filled, capacity - filled) != 1) {
            state->failed = 1;
            return 0;
        }
        size_t copy = state->owned - filled;
        if (copy > state->pending) copy = state->pending;
        state->pending_data += copy;
        state->pending -= copy;
        filled += copy;
    }
    return 1;
}

int fused_history_finish(history *state)
{
    return !state->failed && !state->pending && state->decoded == state->expected &&
           next_block(state, state->output_end, 0) == 0 &&
           state->checksums == 1 && state->consumed == state->encoded &&
           state->decoded == state->expected && state->nth == state->nblocks &&
           state->retained == state->exceptions;
}
