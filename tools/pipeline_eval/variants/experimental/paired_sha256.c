/* Research-only paired SHA-256 over decoded windows and their enclosing chunk. */

#include <stdint.h>
#include <openssl/sha.h>

#if defined(__x86_64__) && defined(__GNUC__)
#include <immintrin.h>
#define LEOPAIRED_X86_SHA 1
#define LEOPAIRED_TARGET __attribute__((target("sha,ssse3,sse4.1")))

/* The SHA-256 round constants in the order specified by FIPS 180-4. */
static const uint32_t round_constant[64] = {
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
};

typedef struct {
    __m128i abef;
    __m128i cdgh;
} RoundState;

static inline LEOPAIRED_TARGET RoundState load_state(const SHA256_CTX *ctx) {
    __m128i dcab = _mm_shuffle_epi32(_mm_loadu_si128((const __m128i *)&ctx->h[0]), 0xb1);
    __m128i efgh = _mm_shuffle_epi32(_mm_loadu_si128((const __m128i *)&ctx->h[4]), 0x1b);
    return (RoundState){_mm_alignr_epi8(dcab, efgh, 8), _mm_blend_epi16(efgh, dcab, 0xf0)};
}

static inline LEOPAIRED_TARGET void store_state(SHA256_CTX *ctx, RoundState state) {
    __m128i feba = _mm_shuffle_epi32(state.abef, 0x1b);
    __m128i dchg = _mm_shuffle_epi32(state.cdgh, 0xb1);
    _mm_storeu_si128((__m128i *)&ctx->h[0], _mm_blend_epi16(feba, dchg, 0xf0));
    _mm_storeu_si128((__m128i *)&ctx->h[4], _mm_alignr_epi8(dchg, feba, 8));
}

static inline LEOPAIRED_TARGET __m128i schedule(__m128i first, __m128i second,
                                               __m128i third, __m128i fourth) {
    first = _mm_sha256msg1_epu32(first, second);
    first = _mm_add_epi32(first, _mm_alignr_epi8(fourth, third, 4));
    return _mm_sha256msg2_epu32(first, fourth);
}

static inline LEOPAIRED_TARGET void rounds(RoundState *a, RoundState *b, unsigned i, __m128i words) {
    __m128i input = _mm_add_epi32(words, _mm_loadu_si128((const __m128i *)&round_constant[i]));
    a->cdgh = _mm_sha256rnds2_epu32(a->cdgh, a->abef, input);
    b->cdgh = _mm_sha256rnds2_epu32(b->cdgh, b->abef, input);
    input = _mm_shuffle_epi32(input, 0x0e);
    a->abef = _mm_sha256rnds2_epu32(a->abef, a->cdgh, input);
    b->abef = _mm_sha256rnds2_epu32(b->abef, b->cdgh, input);
}

static inline LEOPAIRED_TARGET void count_bytes(SHA256_CTX *ctx, size_t size) {
    uint64_t bits = ((uint64_t)ctx->Nh << 32) | ctx->Nl;
    bits += (uint64_t)size << 3;
    ctx->Nl = (uint32_t)bits;
    ctx->Nh = (uint32_t)(bits >> 32);
}

static LEOPAIRED_TARGET void blocks(SHA256_CTX *window, SHA256_CTX *chunk,
                                   const uint8_t *data, size_t size) {
    const __m128i swap = _mm_setr_epi8(3, 2, 1, 0, 7, 6, 5, 4, 11, 10, 9, 8, 15, 14, 13, 12);
    RoundState a = load_state(window);
    RoundState b = load_state(chunk);
    for (size_t start = 0; start < size; start += SHA256_CBLOCK) {
        RoundState previous_a = a;
        RoundState previous_b = b;
        __m128i w0 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + start)), swap);
        __m128i w1 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + start + 16)), swap);
        __m128i w2 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + start + 32)), swap);
        __m128i w3 = _mm_shuffle_epi8(_mm_loadu_si128((const __m128i *)(data + start + 48)), swap);
        rounds(&a, &b, 0, w0);
        rounds(&a, &b, 4, w1);
        rounds(&a, &b, 8, w2);
        rounds(&a, &b, 12, w3);
        for (unsigned i = 16; i < 64; i += 16) {
            w0 = schedule(w0, w1, w2, w3);
            rounds(&a, &b, i, w0);
            w1 = schedule(w1, w2, w3, w0);
            rounds(&a, &b, i + 4, w1);
            w2 = schedule(w2, w3, w0, w1);
            rounds(&a, &b, i + 8, w2);
            w3 = schedule(w3, w0, w1, w2);
            rounds(&a, &b, i + 12, w3);
        }
        a.abef = _mm_add_epi32(a.abef, previous_a.abef);
        a.cdgh = _mm_add_epi32(a.cdgh, previous_a.cdgh);
        b.abef = _mm_add_epi32(b.abef, previous_b.abef);
        b.cdgh = _mm_add_epi32(b.cdgh, previous_b.cdgh);
    }
    store_state(window, a);
    store_state(chunk, b);
    count_bytes(window, size);
    count_bytes(chunk, size);
}
#endif

size_t leo_paired_sha256_context_size(void) {
    return sizeof(SHA256_CTX);
}

int leo_paired_sha256_supported(void) {
#ifdef LEOPAIRED_X86_SHA
    return __builtin_cpu_supports("sha") && __builtin_cpu_supports("ssse3") &&
        __builtin_cpu_supports("sse4.1");
#else
    return 0;
#endif
}

int leo_paired_sha256_init(SHA256_CTX *chunk) {
    return SHA256_Init(chunk);
}

static int update_pair(SHA256_CTX *window, SHA256_CTX *chunk, const uint8_t *data, size_t size) {
#ifdef LEOPAIRED_X86_SHA
    if (window->num == 0 && chunk->num == 0 && size >= SHA256_CBLOCK && leo_paired_sha256_supported()) {
        const size_t full = size - size % SHA256_CBLOCK;
        blocks(window, chunk, data, full);
        size -= full;
        data += full;
    }
#endif
    /* OpenSSL owns buffering, off-block-boundary updates and padding. */
    return SHA256_Update(window, data, size) && SHA256_Update(chunk, data, size);
}

int leo_paired_sha256_window(SHA256_CTX *chunk, const uint8_t *data, size_t size, uint8_t *digest) {
    SHA256_CTX window;
    return SHA256_Init(&window) && update_pair(&window, chunk, data, size) && SHA256_Final(digest, &window);
}

int leo_paired_sha256_window_prefix(SHA256_CTX *chunk, const uint8_t *data, size_t size,
                                    size_t prefix, uint8_t *digest, uint8_t *prefix_digest) {
    SHA256_CTX window;
    if (prefix > size || !SHA256_Init(&window) || !update_pair(&window, chunk, data, prefix)) {
        return 0;
    }
    SHA256_CTX snapshot = window;
    return SHA256_Final(prefix_digest, &snapshot) &&
        update_pair(&window, chunk, data + prefix, size - prefix) && SHA256_Final(digest, &window);
}

int leo_paired_sha256_digest(const SHA256_CTX *chunk, uint8_t *digest) {
    SHA256_CTX snapshot = *chunk;
    return SHA256_Final(digest, &snapshot);
}
