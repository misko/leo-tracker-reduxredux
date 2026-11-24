#define _POSIX_C_SOURCE 200809L
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Diagnostic only. These declarations are from lib/common/huf.h in Zstd 1.5.7. */
size_t HUF_readStats(uint8_t *, size_t, uint32_t *, uint32_t *, uint32_t *, const void *, size_t);
size_t HUF_readDTableX2_wksp(uint32_t *, const void *, size_t, void *, size_t, int);
size_t HUF_decompress4X_usingDTable(void *, size_t, const void *, size_t, const uint32_t *, int);
unsigned HUF_isError(size_t);

enum { code_log_limit = 12, block_limit = 131072, bmi2 = 1, lanes = 4 };

typedef struct { uint32_t offset, encoded, decoded, new_table; } Block;
typedef struct { uint64_t table_ns, decode_ns; uint32_t max_code_log, builds; } Clock;
typedef struct { uint16_t code[1 << code_log_limit]; unsigned incomplete[code_log_limit], log; } Codes;
typedef struct { const uint8_t *src; uint8_t *out; uint8_t *end; size_t bits; } Stream;

static uint64_t now(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts)) abort();
    return (uint64_t)ts.tv_sec * 1000000000 + (uint64_t)ts.tv_nsec;
}

static size_t codebook(Codes *single, const uint8_t *src, size_t size) {
    uint8_t weight[256];
    uint32_t ranks[code_log_limit + 1], n;
    size_t header = HUF_readStats(weight, sizeof(weight), ranks, &n, &single->log, src, size);
    if (HUF_isError(header) || header >= size || !single->log || single->log > code_log_limit)
        return 0;
    unsigned slot = 0;
    for (unsigned w = 1; w <= single->log; ++w) {
        unsigned step = 1u << (w - 1);
        unsigned bits = single->log + 1 - w;
        for (unsigned symbol = 0; symbol < n; ++symbol) {
            if (weight[symbol] != w) continue;
            if (slot + step > (1u << single->log)) return 0;
            for (unsigned i = 0; i < step; ++i)
                single->code[slot++] = (uint16_t)(bits << 8 | symbol);
        }
        /* Longer canonical codes form an initial interval of each suffix table. */
        single->incomplete[bits - 1] = slot >> (single->log + 1 - bits);
    }
    return slot == (1u << single->log) ? header : 0;
}

static void wider(uint32_t *table, unsigned width, const Codes *single) {
    const unsigned limit = 1u << width;
    for (unsigned index = 0; index < limit;) {
        unsigned consumed = 0, emitted = 0, word = index << (32 - width);
        uint32_t value = 0;
        while (emitted < 3) {
            uint16_t symbol = single->code[word >> (32 - single->log)];
            unsigned bits = symbol >> 8;
            if (consumed + bits > width) break;
            value |= (uint32_t)(symbol & 255) << (emitted * 8);
            ++emitted;
            consumed += bits;
            word <<= bits;
        }
        const unsigned remaining = width - consumed;
        const unsigned suffix_size = 1u << remaining;
        const unsigned stop = emitted == 3 ? suffix_size : single->incomplete[remaining];
        const unsigned end = (index & ~(suffix_size - 1)) + stop;
        const uint32_t entry = value | consumed << 24 | emitted << 29;
        for (; index < end; ++index) table[index] = entry;
    }
}

static unsigned le16(const uint8_t *src) {
    return src[0] + 256u * src[1];
}

static int init(Stream *s, const uint8_t *src, size_t size, uint8_t *out, size_t decoded) {
    if (!size || !src[size-1]) return -1;
    const unsigned highest = 31u - (unsigned)__builtin_clz(src[size - 1]);
    *s = (Stream){src, out, out + decoded, (size - 1) * 8 + highest};
    return 0;
}

static inline uint64_t window(const uint8_t *src, size_t bits) {
    uint64_t x;
    memcpy(&x, src + ((bits - 1) / 8) - 7, sizeof(x));
    return x << ((8 - bits) & 7);
}

static inline void emit_three(Stream *s, const uint32_t *table, unsigned width) {
    uint64_t chunk = window(s->src, s->bits);
    uint8_t *out = s->out;
    unsigned consumed = 0;
    for (unsigned i = 0; i < 3; ++i) {
        uint32_t e = table[chunk >> (64 - width)];
        unsigned n = (e >> 24) & 31;
        memcpy(out, &e, sizeof(e));
        chunk <<= n;
        out += e >> 29;
        consumed += n;
    }
    s->bits -= consumed;
    s->out = out;
}

static int finish(Stream *s, const Codes *single) {
    while (s->out < s->end) {
        if (!s->bits) return -1;
        uint64_t x = 0;
        if (s->bits >= 57) {
            x = window(s->src, s->bits);
        } else {
            for (size_t i = 0; i < (s->bits + 7) / 8; ++i)
                x |= (uint64_t)s->src[i] << (i * 8);
            x <<= 64 - s->bits;
        }
        uint16_t e = single->code[x >> (64 - single->log)];
        unsigned n = e >> 8;
        if (n > s->bits) return -1;
        *s->out++ = (uint8_t)e;
        s->bits -= n;
    }
    return s->bits ? -1 : 0;
}

static int decode(const uint8_t *src, size_t size, uint8_t *out, size_t decoded,
                  const Codes *single, const uint32_t *table, unsigned width) {
    if (size < 10) return -1;
    const size_t segment = (decoded + 3) / 4;
    if (segment * 3 >= decoded) return -1;
    Stream stream[lanes];
    size_t start = 6;
    for (unsigned i = 0; i < lanes; ++i) {
        size_t length = i == 3 ? size - start : le16(src + 2 * i);
        size_t count = i == 3 ? decoded - 3 * segment : segment;
        if (length > size - start || init(&stream[i], src + start, length, out + i * segment, count))
            return -1;
        start += length;
    }
    for (;;) {
        unsigned ready = 1;
        for (unsigned i = 0; i < lanes; ++i)
            ready &= stream[i].bits >= 57 && stream[i].end - stream[i].out >= 10;
        if (!ready) break;
        for (unsigned i = 0; i < lanes; ++i) emit_three(&stream[i], table, width);
    }
    /* Keep independent wide lookups when another stream reaches its final bytes first. */
    for (unsigned i = 0; i < lanes; ++i) {
        while (stream[i].bits >= 57 && stream[i].end - stream[i].out >= 10)
            emit_three(&stream[i], table, width);
        if (finish(&stream[i], single)) return -1;
    }
    return 0;
}

int huffman_trial(const uint8_t *source, size_t size, const Block *blocks, size_t count,
                  unsigned width, uint8_t *result, size_t output_bytes, Clock *clock) {
    if (width && width != 12 && width != 14 && width != 16) return -1;
    Codes codes;
    uint32_t stock[(1 << code_log_limit) + 1];
    uint64_t workspace[2048];
    uint32_t *wide = width ? malloc(sizeof(*wide) * (1u << width)) : NULL;
    if (width && !wide) return -1;
    *clock = (Clock){0};
    size_t written = 0;
    int status = -1;
    for (size_t i = 0; i < count; ++i) {
        const Block b = blocks[i];
        if (b.offset > size || b.encoded > size - b.offset || b.decoded > block_limit ||
            b.decoded > output_bytes - written || (!i && !b.new_table)) goto cleanup;
        const uint8_t *src = source + b.offset;
        size_t table_bytes = 0;
        if (b.new_table) {
            uint64_t t = now();
            if (width) {
                table_bytes = codebook(&codes, src, b.encoded);
                if (!table_bytes || codes.log > width) goto cleanup;
                wider(wide, width, &codes);
                if (codes.log > clock->max_code_log) clock->max_code_log = codes.log;
            } else {
                stock[0] = 0x0c00000c;
                table_bytes = HUF_readDTableX2_wksp(stock, src, b.encoded, workspace, sizeof(workspace), bmi2);
                if (HUF_isError(table_bytes)) goto cleanup;
            }
            if (table_bytes >= b.encoded) goto cleanup;
            clock->table_ns += now() - t;
            ++clock->builds;
        }
        uint64_t t = now();
        if (width) {
            if (decode(src + table_bytes, b.encoded - table_bytes, result + written, b.decoded, &codes, wide, width))
                goto cleanup;
        } else if (HUF_decompress4X_usingDTable(result + written, b.decoded, src + table_bytes,
                                               b.encoded - table_bytes, stock, bmi2) != b.decoded) {
            goto cleanup;
        }
        clock->decode_ns += now() - t;
        written += b.decoded;
    }
    status = written == output_bytes ? 0 : -1;
cleanup:
    free(wide);
    return status;
}
