/* Research reader for authenticated, match-free Zstandard block selections. */
#define ZSTD_STATIC_LINKING_ONLY
#include <zstd.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { BLOCK_MAX = 128 * 1024 };

typedef struct {
    uint32_t encoded, length, decoded, count, origin;
} block;

typedef struct {
    uint64_t requested_blocks, requested_encoded, requested_decoded;
    uint64_t dependency_blocks, dependency_encoded, dependency_decoded;
} counts;

typedef struct {
    ZSTD_DCtx *decoder;
    uint32_t resident, active;
    unsigned char output[BLOCK_MAX];
} reader;

reader *legacy_open(void)
{
    reader *state = malloc(sizeof(*state));
    if (!state) return NULL;
    state->decoder = ZSTD_createDCtx();
    if (!state->decoder || ZSTD_isError(ZSTD_decompressBegin(state->decoder))) {
        ZSTD_freeDCtx(state->decoder);
        free(state);
        return NULL;
    }
    state->resident = state->active = UINT32_MAX;
    return state;
}

void legacy_close(reader *state)
{
    ZSTD_freeDCtx(state->decoder);
    free(state);
}

static int decode(reader *state, const unsigned char *source, size_t size,
                  const block *entry)
{
    if (entry->encoded > size || entry->length > size - entry->encoded ||
        entry->count > BLOCK_MAX) return 0;
    size_t bytes = ZSTD_decompressBlock(state->decoder, state->output, BLOCK_MAX,
                                       source + entry->encoded, entry->length);
    return !ZSTD_isError(bytes) && bytes == entry->count;
}

int legacy_span(reader *state, const unsigned char *source, size_t size,
                const block *blocks, uint32_t nblocks, uint32_t first,
                uint32_t start, uint32_t wanted, unsigned char *output, counts *measured)
{
    for (uint32_t i = first; wanted && i < nblocks; i++) {
        const block *entry = blocks + i;
        if (entry->origin > i || start < entry->decoded ||
            start - entry->decoded >= entry->count) return 0;
        if (state->resident != i) {
            if (entry->origin < i && state->active != entry->origin) {
                const block *origin = blocks + entry->origin;
                if (origin->origin != entry->origin || !decode(state, source, size, origin)) return 0;
                measured->dependency_blocks++;
                measured->dependency_encoded += origin->length;
                measured->dependency_decoded += origin->count;
            }
            if (!decode(state, source, size, entry)) return 0;
            state->active = entry->origin;
            state->resident = i;
            measured->requested_blocks++;
            measured->requested_encoded += entry->length;
            measured->requested_decoded += entry->count;
        }
        uint32_t offset = start - entry->decoded;
        uint32_t copied = entry->count - offset;
        if (copied > wanted) copied = wanted;
        memcpy(output, state->output + offset, copied);
        output += copied;
        wanted -= copied;
        start += copied;
    }
    return wanted == 0;
}
