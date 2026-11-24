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
    uint32_t table_owner, literal_bytes, literal_count, table_replays;
    unsigned char *seed;
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
    state->table_owner = UINT32_MAX;
    state->literal_bytes = state->literal_count = state->table_replays = 0;
    state->seed = NULL;
    return state;
}

void legacy_close(reader *state)
{
    ZSTD_freeDCtx(state->decoder);
    free(state->seed);
    free(state);
}

size_t legacy_scratch(const reader *state)
{
    return sizeof(*state) + ZSTD_sizeof_DCtx(state->decoder) +
           (state->seed ? (size_t)state->literal_bytes + 1 : 0);
}

int legacy_configure_origin(reader *state, uint32_t ordinal,
                            uint32_t literal_bytes, uint32_t literal_count)
{
    if (state->seed || ordinal == UINT32_MAX || !literal_bytes || literal_bytes >= BLOCK_MAX ||
        !literal_count || literal_count > BLOCK_MAX) return 0;
    state->seed = malloc((size_t)literal_bytes + 1);
    if (!state->seed) return 0;
    state->table_owner = ordinal;
    state->literal_bytes = literal_bytes;
    state->literal_count = literal_count;
    return 1;
}

uint32_t legacy_origin_replays(const reader *state)
{
    return state->table_replays;
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
        if (i == state->table_owner || entry->origin > i || start < entry->decoded ||
            start - entry->decoded >= entry->count) return 0;
        if (state->resident != i) {
            if (entry->origin < i && state->active != entry->origin) {
                const block *origin = blocks + entry->origin;
                if (origin->origin != entry->origin) return 0;
                measured->dependency_blocks++;
                if (entry->origin == state->table_owner) {
                    uint32_t bytes = state->literal_bytes;
                    if (origin->encoded > size || origin->length > size - origin->encoded ||
                        bytes >= origin->length || state->literal_count >= origin->count) return 0;
                    const unsigned char *original = source + origin->encoded;
                    if ((original[0] & 3) != 2 || !original[bytes]) return 0;
                    memcpy(state->seed, original, bytes);
                    state->seed[bytes] = 0;
                    size_t regenerated = ZSTD_decompressBlock(state->decoder, state->output, BLOCK_MAX,
                                                              state->seed, (size_t)bytes + 1);
                    if (ZSTD_isError(regenerated) || regenerated != state->literal_count) return 0;
                    state->table_replays++;
                    measured->dependency_encoded += bytes + 1;
                    measured->dependency_decoded += state->literal_count;
                } else {
                    if (!decode(state, source, size, origin)) return 0;
                    measured->dependency_encoded += origin->length;
                    measured->dependency_decoded += origin->count;
                }
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
