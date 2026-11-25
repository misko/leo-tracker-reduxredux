#define ZSTD_STATIC_LINKING_ONLY
#define ZSTD_DISABLE_DEPRECATE_WARNINGS
#include <zstd.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

/* Private research binding to the pinned Zstd 1.5.7 X2 DTable layout. */
size_t HUF_readStats(uint8_t *, size_t, uint32_t *, uint32_t *, uint32_t *, const void *, size_t);
size_t HUF_readDTableX2_wksp(uint32_t *, const void *, size_t, void *, size_t, int);
size_t HUF_decompress4X_usingDTable(void *, size_t, const void *, size_t, const uint32_t *, int);
unsigned HUF_isError(size_t);
uint64_t ZSTD_XXH64(const void *, size_t, uint64_t);

enum { log_limit = 12, block_limit = 131072, streams = 4 };
typedef struct {
    uint32_t offset, encoded, decoded, fresh, block_offset, mixed_encoded;
} Literal;
typedef struct {
    uint32_t pair_count, different_tables, singletons, tables, mixed_blocks, history_bytes;
} Work;
typedef struct {
    uint32_t x2[1 + (1u << log_limit)];
    uint8_t code_bits[256];
    unsigned log;
} Table;
typedef struct { const uint8_t *in; uint8_t *out, *end; size_t bits; } Stream;

static size_t setup_table(Table *table, const uint8_t *data, size_t size) {
    uint8_t weight[256];
    uint32_t ranks[log_limit + 1], symbols, code_log;
    size_t stats = HUF_readStats(weight, sizeof(weight), ranks, &symbols, &code_log, data, size);
    if (HUF_isError(stats) || stats >= size || !code_log || code_log > log_limit) return 0;
    memset(table->code_bits, 0, sizeof(table->code_bits));
    for (unsigned s = 0; s < symbols; ++s)
        if (weight[s]) table->code_bits[s] = (uint8_t)(code_log + 1 - weight[s]);
    uint64_t workspace[2048];
    table->x2[0] = 0x0c00000c;
    size_t used = HUF_readDTableX2_wksp(table->x2, data, size, workspace, sizeof(workspace), 0);
    table->log = (table->x2[0] >> 16) & 255;
    if (HUF_isError(used) || used != stats || !table->log || table->log > log_limit ||
        ((table->x2[0] >> 8) & 255) != 1) return 0;
    return used;
}

static unsigned read_le16(const uint8_t *p) { return p[0] + (unsigned)p[1] * 256u; }

static int prepare_streams(Stream *s, const uint8_t *data, size_t size, uint8_t *out, size_t count) {
    size_t segment = (count + 3) / 4;
    if (size < 10 || segment * 3 >= count) return -1;
    size_t here = 6;
    for (unsigned i = 0; i < streams; ++i) {
        size_t length = i == streams - 1 ? size - here : read_le16(data + 2 * i);
        size_t output = i == streams - 1 ? count - segment * 3 : segment;
        if (!length || length > size - here || !data[here + length - 1]) return -1;
        unsigned top = 31u - (unsigned)__builtin_clz(data[here + length - 1]);
        s[i] = (Stream){data + here, out + i * segment, out + i * segment + output, (length - 1) * 8 + top};
        here += length;
    }
    return 0;
}

static inline uint64_t next_word(const Stream *s) {
    uint64_t word;
    memcpy(&word, s->in + ((s->bits - 1) / 8) - 7, sizeof(word));
    return word << ((8 - s->bits) & 7);
}

static inline __attribute__((always_inline)) void emit_four(Stream *s, const Table *table) {
    uint64_t word = next_word(s);
    uint8_t *out = s->out;
    unsigned consumed = 0;
    for (unsigned i = 0; i < 4; ++i) {
        uint32_t entry = table->x2[1 + (word >> (64 - table->log))];
        unsigned bits = (entry >> 16) & 255;
        memcpy(out, &entry, 2);
        out += entry >> 24;
        word <<= bits;
        consumed += bits;
    }
    s->bits -= consumed;
    s->out = out;
}

static int finish_stream(Stream *s, const Table *table) {
    while (s->out < s->end) {
        if (!s->bits) return -1;
        uint64_t word = 0;
        if (s->bits >= 57) word = next_word(s);
        else {
            for (size_t i = 0; i < (s->bits + 7) / 8; ++i) word |= (uint64_t)s->in[i] << (8 * i);
            word <<= 64 - s->bits;
        }
        uint32_t entry = table->x2[1 + (word >> (64 - table->log))];
        uint8_t first = (uint8_t)entry;
        unsigned bits = table->code_bits[first];
        if (!bits || bits > s->bits) return -1;
        *s->out++ = first;
        s->bits -= bits;
    }
    return s->bits == 0 ? 0 : -1;
}

static int pair(const uint8_t *const in[2], const size_t encoded[2], uint8_t *const out[2],
                const size_t decoded[2], const Table *const tables[2]) {
    Stream lane[2 * streams];
    if (prepare_streams(lane, in[0], encoded[0], out[0], decoded[0]) ||
        prepare_streams(lane + streams, in[1], encoded[1], out[1], decoded[1])) return -1;
    for (;;) {
        size_t repeat = block_limit;
        for (unsigned i = 0; i < 2 * streams; ++i) {
            size_t bits = lane[i].bits < 57 ? 0 : 1 + (lane[i].bits - 57) / (4 * log_limit);
            size_t symbols = (size_t)(lane[i].end - lane[i].out) / 8;
            size_t safe = bits < symbols ? bits : symbols;
            if (safe < repeat) repeat = safe;
        }
        if (!repeat) break;
        for (; repeat; --repeat) {
            for (unsigned i = 0; i < streams; ++i) emit_four(&lane[i], tables[0]);
            for (unsigned i = streams; i < 2 * streams; ++i) emit_four(&lane[i], tables[1]);
        }
    }
    for (unsigned i = 0; i < 2 * streams; ++i) {
        const Table *table = tables[i / streams];
        while (lane[i].bits >= 57 && lane[i].end - lane[i].out >= 8) emit_four(&lane[i], table);
        if (finish_stream(&lane[i], table)) return -1;
    }
    return 0;
}

/* No preceding block in an admitted plan sets sequence tables or rep offsets.
 * This block supplies its own Huffman table. The normal decoder gets the exact
 * original header, block and output history, with no synthetic frame bytes. */
static int decode_mixed(const uint8_t *input, size_t size, const ZSTD_frameHeader *header,
                        Literal b, uint8_t *raw, size_t written, Work *work) {
    if (!b.fresh || b.block_offset > size - 7 || b.mixed_encoded > size - 7 - b.block_offset ||
        b.mixed_encoded > header->blockSizeMax || b.block_offset < header->headerSize ||
        ((input[b.block_offset] & 1) && header->frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN))
        return -1;
    ZSTD_DCtx *context = ZSTD_createDCtx();
    if (!context) return -1;
    int ok = 0;
    if (!ZSTD_isError(ZSTD_decompressBegin(context))) {
        size_t at = 0;
        while (at < header->headerSize) {
            size_t n = ZSTD_nextSrcSizeToDecompress(context);
            if (!n || n > header->headerSize - at ||
                ZSTD_decompressContinue(context, NULL, 0, input + at, n) != 0) break;
            at += n;
        }
        size_t history = written < header->windowSize ? written : (size_t)header->windowSize;
        ok = at == header->headerSize && ZSTD_nextSrcSizeToDecompress(context) == 3 &&
             ZSTD_decompressContinue(context, NULL, 0, input + b.block_offset, 3) == 0 &&
             ZSTD_nextSrcSizeToDecompress(context) == b.mixed_encoded &&
             (!history || ZSTD_insertBlock(context, raw + written - history, history) == history) &&
             ZSTD_decompressContinue(context, raw + written, b.decoded, input + b.block_offset + 3,
                                     b.mixed_encoded) == b.decoded;
        if (ok) {
            ++work->mixed_blocks;
            work->history_bytes = (uint32_t)history;
        }
    }
    ZSTD_freeDCtx(context);
    return ok ? 0 : -1;
}

/* Plan is derived from one full immutable frame by the Python authority port. */
int literal_pair_frame(const uint8_t *input, size_t size, const Literal *plan, size_t count,
                       uint8_t *raw, size_t decoded_total, Work *work) {
    ZSTD_frameHeader header;
    if (ZSTD_versionNumber() != 10507 || ZSTD_getFrameHeader(&header, input, size) ||
        header.frameType != ZSTD_frame || !header.checksumFlag || header.dictID ||
        (header.frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN && header.frameContentSize != decoded_total) ||
        !count || !plan[0].fresh || size < 8 || ZSTD_findFrameCompressedSize(input, size) != size) return -1;
    *work = (Work){0};
    Table storage[2];
    unsigned current = 1;
    size_t written = 0, last = header.headerSize;
    for (size_t i = 0; i < count;) {
        const unsigned n = !plan[i].mixed_encoded && count - i > 1 && !plan[i+1].mixed_encoded ? 2 : 1;
        const uint8_t *in[2];
        uint8_t *out[2];
        size_t encoded[2], decoded[2];
        const Table *tables[2];
        for (unsigned j = 0; j < n; ++j) {
            Literal b = plan[i + j];
            if (b.block_offset != last || b.offset < last + 3 || b.offset > size - 5 ||
                b.encoded > size - 5 - b.offset ||
                b.decoded > decoded_total - written || b.decoded > header.blockSizeMax || !b.decoded ||
                b.encoded > header.blockSizeMax || b.fresh > 1) return -1;
            size_t used = 0;
            if (b.fresh) {
                current ^= 1;
                used = setup_table(storage + current, input + b.offset, b.encoded);
                if (!used) return -1;
                ++work->tables;
            }
            tables[j] = storage + current;
            in[j] = input + b.offset + used;
            encoded[j] = b.encoded - used;
            out[j] = raw + written;
            decoded[j] = b.decoded;
            written += b.decoded;
            last = b.offset + b.encoded + 1; /* Literal-only block's zero sequence count. */
        }
        if (plan[i].mixed_encoded) {
            if (work->mixed_blocks || decode_mixed(input, size, &header, plan[i], raw,
                                                  written - plan[i].decoded, work)) return -1;
            last = (size_t)plan[i].block_offset + 3 + plan[i].mixed_encoded;
        } else if (n == 2) {
            if (pair(in, encoded, out, decoded, tables)) return -1;
            ++work->pair_count;
            work->different_tables += tables[0] != tables[1];
        } else {
            if (HUF_decompress4X_usingDTable(out[0], decoded[0], in[0], encoded[0], tables[0]->x2, 0) != decoded[0])
                return -1;
            ++work->singletons;
        }
        i += n;
    }
    uint32_t expected = (uint32_t)input[size-4] | (uint32_t)input[size-3] << 8 |
                        (uint32_t)input[size-2] << 16 | (uint32_t)input[size-1] << 24;
    return last == size - 4 && written == decoded_total &&
           (uint32_t)ZSTD_XXH64(raw, written, 0) == expected ? 0 : -1;
}
