#define ZSTD_STATIC_LINKING_ONLY
#define ZSTD_DISABLE_DEPRECATE_WARNINGS
#include <zstd.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

/* Private research binding to the pinned Zstd 1.5.7 X2 DTable layout. */
size_t HUF_readDTableX2_wksp(uint32_t *, const void *, size_t, void *, size_t, int);
size_t HUF_decompress4X_usingDTable(void *, size_t, const void *, size_t, const uint32_t *, int);
unsigned HUF_isError(size_t);
uint64_t ZSTD_XXH64(const void *, size_t, uint64_t);
typedef struct XXH64_state_s XXH64_state;
XXH64_state *ZSTD_XXH64_createState(void);
int ZSTD_XXH64_freeState(XXH64_state *);
int ZSTD_XXH64_reset(XXH64_state *, uint64_t);
int ZSTD_XXH64_update(XXH64_state *, const void *, size_t);
uint64_t ZSTD_XXH64_digest(const XXH64_state *);

enum { log_limit = 12, block_limit = 131072, streams = 4 };
typedef struct {
    uint32_t offset, encoded, decoded, fresh, block_offset, mixed_encoded;
} Literal;
typedef struct {
    uint32_t pair_count, different_tables, singletons, tables, mixed_blocks, history_bytes;
} Work;
typedef struct {
    uint32_t x2[1 + (1u << log_limit)];
    unsigned log;
} Table;
typedef struct { const uint8_t *in; uint8_t *out, *end; size_t bits; } Stream;

static size_t setup_table(Table *table, const uint8_t *data, size_t size) {
    uint64_t workspace[2048];
    table->x2[0] = 0x0c00000c;
    size_t used = HUF_readDTableX2_wksp(table->x2, data, size, workspace, sizeof(workspace), 0);
    table->log = (table->x2[0] >> 16) & 255;
    if (HUF_isError(used) || !used || used >= size || !table->log || table->log > log_limit ||
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
        unsigned index = (unsigned)(word >> (64 - table->log));
        uint8_t first = (uint8_t)table->x2[1 + index];
        /* All X2 entries for a first symbol lie in its unique aligned prefix
         * run. Search only the run's sibling subtrees at the exact tail. */
        unsigned width = 1, limit = 1u << table->log, bits = table->log;
        while (width < limit && (uint8_t)table->x2[1 + ((index ^ width) & ~(width - 1))] == first) {
            width <<= 1;
            --bits;
        }
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
                        Literal b, uint8_t *out, size_t history, Work *work, size_t *context_bytes) {
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
        ok = at == header->headerSize && ZSTD_nextSrcSizeToDecompress(context) == 3 &&
             ZSTD_decompressContinue(context, NULL, 0, input + b.block_offset, 3) == 0 &&
             ZSTD_nextSrcSizeToDecompress(context) == b.mixed_encoded &&
             (!history || ZSTD_insertBlock(context, out - history, history) == history) &&
             ZSTD_decompressContinue(context, out, b.decoded, input + b.block_offset + 3, b.mixed_encoded) == b.decoded;
        if (ok) {
            ++work->mixed_blocks;
            work->history_bytes = (uint32_t)history;
        }
    }
    if (context_bytes) *context_bytes = ZSTD_sizeof_DCtx(context);
    ZSTD_freeDCtx(context);
    return ok ? 0 : -1;
}

typedef struct {
    const uint8_t *input;
    const Literal *plan;
    size_t size, count, total, i, last, written;
    unsigned current;
    ZSTD_frameHeader header;
    Table storage[2];
    Work work;
} Member;

static int header_for(ZSTD_frameHeader *header, const void *input, size_t size, size_t total) {
    return size >= 8 && ZSTD_versionNumber() == 10507 && !ZSTD_getFrameHeader(header, input, size) &&
           header->frameType == ZSTD_frame && header->checksumFlag && !header->dictID && header->windowSize &&
           (header->frameContentSize == ZSTD_CONTENTSIZE_UNKNOWN || header->frameContentSize == total);
}

static void begin(Member *m, const uint8_t *input, size_t size, const Literal *plan, size_t count, size_t total) {
    m->input = input;
    m->size = size;
    m->plan = plan;
    m->count = count;
    m->total = total;
    m->last = m->header.headerSize;
    m->current = 1;
}

/* A caller provides enough consecutive destination room for a pair and, only
 * at the mixed seam, the preceding contiguous history immediately before it. */
static size_t next_group(Member *m, uint8_t *destination, size_t capacity, size_t history,
                         size_t *context_bytes) {
    const Literal *row = m->plan + m->i;
    const unsigned n = !row->mixed_encoded && m->count - m->i > 1 && !row[1].mixed_encoded ? 2 : 1;
    const uint8_t *in[2];
    uint8_t *out[2];
    size_t encoded[2], decoded[2], used_bytes = 0;
    const Table *tables[2];
    for (unsigned j = 0; j < n; ++j) {
        Literal b = row[j];
        if (b.block_offset != m->last || b.offset < m->last + 3 || b.offset > m->size - 5 ||
            b.encoded > m->size - 5 - b.offset || b.decoded > capacity - used_bytes ||
            b.decoded > m->total - m->written || b.decoded > m->header.blockSizeMax || !b.decoded ||
            b.encoded > m->header.blockSizeMax || b.fresh > 1) return 0;
        size_t used = 0;
        if (b.fresh) {
            m->current ^= 1;
            used = setup_table(m->storage + m->current, m->input + b.offset, b.encoded);
            if (!used) return 0;
            ++m->work.tables;
        }
        tables[j] = m->storage + m->current;
        in[j] = m->input + b.offset + used;
        encoded[j] = b.encoded - used;
        out[j] = destination + used_bytes;
        decoded[j] = b.decoded;
        used_bytes += b.decoded;
        m->written += b.decoded;
        m->last = b.offset + b.encoded + 1;
    }
    if (row->mixed_encoded) {
        if (m->work.mixed_blocks || decode_mixed(m->input, m->size, &m->header, *row, destination,
                                               history, &m->work, context_bytes)) return 0;
        m->last = (size_t)row->block_offset + 3 + row->mixed_encoded;
    } else if (n == 2) {
        if (pair(in, encoded, out, decoded, tables)) return 0;
        ++m->work.pair_count;
        m->work.different_tables += tables[0] != tables[1];
    } else {
        if (HUF_decompress4X_usingDTable(out[0], decoded[0], in[0], encoded[0], tables[0]->x2, 0) != decoded[0])
            return 0;
        ++m->work.singletons;
    }
    m->i += n;
    return used_bytes;
}

static uint32_t read_le(const uint8_t *data, unsigned size) {
    uint32_t value = 0;
    for (unsigned i = 0; i < size; ++i) value |= (uint32_t)data[i] << (8 * i);
    return value;
}

static int complete(const Member *m, uint64_t checksum) {
    return m->i == m->count && m->last == m->size - 4 && m->written == m->total &&
           (uint32_t)checksum == read_le(m->input + m->last, 4);
}

int literal_pair_frame(const uint8_t *input, size_t size, const Literal *plan, size_t count,
                       uint8_t *raw, size_t decoded_total, Work *work) {
    Member m = {0};
    if (!header_for(&m.header, input, size, decoded_total) || !count || !plan[0].fresh ||
        ZSTD_findFrameCompressedSize(input, size) != size) return -1;
    begin(&m, input, size, plan, count, decoded_total);
    while (m.i < count) {
        size_t history = m.written < m.header.windowSize ? m.written : (size_t)m.header.windowSize;
        if (!next_group(&m, raw + m.written, m.total - m.written, history, NULL)) return -1;
    }
    *work = m.work;
    return complete(&m, ZSTD_XXH64(raw, m.written, 0)) ? 0 : -1;
}

enum { max_plan_rows = 4096, max_history = 8 << 20 };
typedef struct { size_t spill_bytes, seam_copy_bytes, workspace_bytes, mixed_zstd_context_bytes; } OwnedWork;
typedef struct {
    Member member;
    Literal *plan;
    XXH64_state *checksum;
    uint8_t *seam;
    const uint8_t *previous;
    size_t owned, pending;
    OwnedWork work;
    int failed;
} Owned;

/* Inspect original headers in one bounded traversal. New Huffman tables are
 * built in next_group() only; a second table parse is needed at the seam only. */
static int plan_owned(Owned *s, const uint8_t *input, size_t size, size_t total) {
    size_t position = s->member.header.headerSize, n = 0, raw_bytes = 0, mixed = max_plan_rows;
    unsigned last;
    do {
        if (n == max_plan_rows || position > size - 7) return 0;
        uint32_t packed = read_le(input + position, 3);
        uint32_t encoded = packed >> 3;
        last = packed & 1;
        if (((packed >> 1) & 3) != 2 || encoded < 5 || encoded > s->member.header.blockSizeMax ||
            encoded > size - 7 - position) return 0;
        uint8_t mode = input[position + 3] & 3;
        uint8_t form = (input[position + 3] >> 2) & 3;
        if (mode < 2 || !form || (!n && mode != 2)) return 0;
        static const unsigned head[] = {0, 3, 4, 5}, widths[] = {0, 10, 14, 18};
        uint64_t literal = read_le(input + position + 3, head[form] < 4 ? head[form] : 4) >> 4;
        if (form == 3) literal |= (uint64_t)input[position + 7] << 28;
        uint32_t plain = (uint32_t)(literal & ((1u << widths[form]) - 1u));
        uint32_t bytes = (uint32_t)(literal >> widths[form]);
        if (!plain || plain > s->member.header.blockSizeMax || !bytes ||
            head[form] + bytes >= encoded || plain > total - raw_bytes) return 0;
        uint32_t seq = (uint32_t)position + 3 + head[form] + bytes;
        unsigned has_sequence = input[seq] != 0;
        if (has_sequence) {
            if (mixed != max_plan_rows || mode != 2 ||
                (last && s->member.header.frameContentSize != ZSTD_CONTENTSIZE_UNKNOWN)) return 0;
            mixed = n;
        } else if (seq + 1 != position + 3 + encoded) return 0;
        s->plan[n++] = (Literal){(uint32_t)position + 3 + head[form], bytes, plain,
                                mode == 2, (uint32_t)position, has_sequence ? encoded : 0};
        raw_bytes += plain;
        position += 3 + encoded;
    } while (!last);
    if (position != size - 4) return 0;
    if (mixed == max_plan_rows) {
        if (raw_bytes != total) return 0;
    } else {
        Literal *block = s->plan + mixed;
        size_t match = total - raw_bytes;
        if (match < 3 || match > s->member.header.blockSizeMax - block->decoded) return 0;
        block->decoded += (uint32_t)match;
    }
    begin(&s->member, input, size, s->plan, n, total);
    return 1;
}

void literal_pair_owned_close(Owned *s) {
    if (!s) return;
    ZSTD_XXH64_freeState(s->checksum);
    free(s->seam);
    free(s->plan);
    free(s);
}

Owned *literal_pair_owned_open(const uint8_t *input, size_t size, size_t total, size_t owned) {
    ZSTD_frameHeader header;
    if (!header_for(&header, input, size, total) || !owned || total > UINT32_MAX || size > UINT32_MAX ||
        owned < header.windowSize + header.blockSizeMax || header.windowSize > max_history || total % owned ||
        !header.blockSizeMax || header.blockSizeMax > block_limit) return NULL;
    Owned *s = calloc(1, sizeof(*s));
    if (!s) return NULL;
    s->owned = owned;
    s->member.header = header;
    s->plan = malloc(max_plan_rows * sizeof(Literal));
    s->checksum = ZSTD_XXH64_createState();
    if (!s->plan || !s->checksum || ZSTD_XXH64_reset(s->checksum, 0) || !plan_owned(s, input, size, total)) {
        literal_pair_owned_close(s);
        return NULL;
    }
    s->work.workspace_bytes = sizeof(*s) + max_plan_rows * sizeof(Literal);
    return s;
}

size_t literal_pair_owned_scratch(const Owned *s) { return s->work.workspace_bytes; }

/* Buffers are owned by the caller. Its immediately preceding allocation
 * stays live until this call returns. Older yielded output is untouched. */
int literal_pair_owned_read(Owned *s, uint8_t *out, size_t capacity) {
    Member *m = &s->member;
    if (s->failed || capacity < s->owned + 2 * m->header.blockSizeMax ||
        s->pending > s->owned || (s->pending && !s->previous)) return 0;
    size_t filled = s->pending;
    if (filled) {
        memcpy(out, s->previous + s->owned, filled);
        s->work.spill_bytes += filled;
    }
    while (filled < s->owned) {
        if (m->i >= m->count) break;
        const Literal *row = m->plan + m->i;
        size_t history = m->written < m->header.windowSize ? m->written : (size_t)m->header.windowSize;
        size_t count;
        if (row->mixed_encoded && history > filled) {
            if (!s->previous || history - filled > s->owned) break;
            size_t seam_bytes = history + m->header.blockSizeMax;
            s->seam = malloc(seam_bytes);
            if (!s->seam) break;
            s->work.workspace_bytes += seam_bytes;
            memcpy(s->seam, s->previous + s->owned - (history - filled), history - filled);
            memcpy(s->seam + history - filled, out, filled);
            count = next_group(m, s->seam + history, m->header.blockSizeMax, history,
                               &s->work.mixed_zstd_context_bytes);
            if (count) memcpy(out + filled, s->seam + history, count);
            s->work.seam_copy_bytes += history + count;
            free(s->seam);
            s->seam = NULL;
        } else {
            count = next_group(m, out + filled, capacity - filled, history, &s->work.mixed_zstd_context_bytes);
        }
        if (!count) break;
        filled += count;
    }
    if (filled < s->owned || ZSTD_XXH64_update(s->checksum, out, s->owned)) {
        s->failed = 1;
        return 0;
    }
    s->pending = filled - s->owned;
    s->previous = out;
    return 1;
}

int literal_pair_owned_finish(const Owned *s, Work *work, OwnedWork *owned) {
    *work = s->member.work;
    *owned = s->work;
    return !s->failed && !s->pending && complete(&s->member, ZSTD_XXH64_digest(s->checksum));
}
