/* Roll eight physical pilot tones and mix each original anchor before magnitude. */
#include <math.h>
#include <immintrin.h>
#include <stdint.h>
#include <string.h>

enum { ntone = 8, width = 44, tile = 1024 };
typedef double V4 __attribute__((vector_size(32)));
typedef float F4 __attribute__((vector_size(16)));
typedef float F8 __attribute__((vector_size(32)));
typedef struct { double r, i; } Z;

static V4 broadcast(double x) { return (V4){x, x, x, x}; }

static void transpose(const float input[tile][ntone], float out[ntone][tile], int size) {
    int p = 0;
    for (; p+8 <= size; p += 8) {
        __m256 q[8], half[8];
        for (int j=0; j<8; j+=2) {
            q[j] = _mm256_unpacklo_ps(_mm256_loadu_ps(input[p+j]), _mm256_loadu_ps(input[p+j+1]));
            q[j+1] = _mm256_unpackhi_ps(_mm256_loadu_ps(input[p+j]), _mm256_loadu_ps(input[p+j+1]));
        }
        for (int j=0; j<8; j+=4) {
            half[j] = _mm256_shuffle_ps(q[j], q[j+2], 0x44);
            half[j+1] = _mm256_shuffle_ps(q[j], q[j+2], 0xee);
            half[j+2] = _mm256_shuffle_ps(q[j+1], q[j+3], 0x44);
            half[j+3] = _mm256_shuffle_ps(q[j+1], q[j+3], 0xee);
        }
        for (int j=0; j<4; ++j) {
            _mm256_storeu_ps(out[j]+p, _mm256_permute2f128_ps(half[j], half[j+4], 0x20));
            _mm256_storeu_ps(out[j+4]+p, _mm256_permute2f128_ps(half[j], half[j+4], 0x31));
        }
    }
    for (; p<size; ++p)
        for (int j=0; j<8; ++j) out[j][p] = input[p][j];
}

static void roll(const float *restrict xr, const float *restrict xi,
                 const float *restrict norm, int first, int size,
                 const Z *restrict inv, const Z *restrict end, const Z *restrict coefficients,
                 const Z *restrict seeds, float re[ntone][tile], float im[ntone][tile]) {
    _Alignas(32) float ar[tile][ntone], ai[tile][ntone];
    for (int group = 0; group < 2; ++group) {
        int j = 4*group;
        V4 yr = {0}, yi = {0};
        V4 vr = {inv[j].r, inv[j+1].r, inv[j+2].r, inv[j+3].r};
        V4 vi = {inv[j].i, inv[j+1].i, inv[j+2].i, inv[j+3].i};
        V4 er = {end[j].r, end[j+1].r, end[j+2].r, end[j+3].r};
        V4 ei = {end[j].i, end[j+1].i, end[j+2].i, end[j+3].i};
        V4 cr = {coefficients[j].r, coefficients[j+1].r, coefficients[j+2].r, coefficients[j+3].r};
        V4 ci = {coefficients[j].i, coefficients[j+1].i, coefficients[j+2].i, coefficients[j+3].i};
        for (int d = 0; d < width; ++d) {
            const Z *tone = seeds + d*ntone+j;
            const V4 tr = {tone[0].r, tone[1].r, tone[2].r, tone[3].r};
            const V4 ti = {tone[0].i, tone[1].i, tone[2].i, tone[3].i};
            const V4 x = broadcast(xr[first+d]), y = broadcast(xi[first+d]);
            yr += x*tr-y*ti;
            yi += x*ti+y*tr;
        }
        for (int t = 0; t < size; ++t) {
            const int p = first+t;
            const V4 normal = broadcast(norm[p]);
            F4 out_r = __builtin_convertvector((yr*cr-yi*ci)*normal, F4);
            F4 out_i = __builtin_convertvector((yr*ci+yi*cr)*normal, F4);
            memcpy(ar[t]+j, &out_r, sizeof(out_r));
            memcpy(ai[t]+j, &out_i, sizeof(out_i));
            const V4 dlr = yr-broadcast(xr[p]), dli = yi-broadcast(xi[p]);
            const V4 nr = broadcast(xr[p+width]), ni = broadcast(xi[p+width]);
            yr = (dlr*vr-dli*vi)+(nr*er-ni*ei);
            yi = (dlr*vi+dli*vr)+(nr*ei+ni*er);
        }
    }
    transpose(ar, re, size);
    transpose(ai, im, size);
}

typedef struct { F8 r, i; } Z8;

static Z8 narrow(const Z *input) {
    Z8 out;
    for (int k=0; k<ntone; ++k) {
        out.r[k] = (float)input[k].r;
        out.i[k] = (float)input[k].i;
    }
    return out;
}

static void roll8(const float *restrict xr, const float *restrict xi,
                  const float *restrict norm, int first, int size,
                  const Z *restrict inv, const Z *restrict end, const Z *restrict coefficients,
                  const Z *restrict seeds, float re[ntone][tile], float im[ntone][tile]) {
    _Alignas(32) float ar[tile][ntone], ai[tile][ntone];
    const Z8 undo = narrow(inv), tail = narrow(end), scale = narrow(coefficients);
    for (int start=0; start<size; start+=128) {
        Z8 v = {0};
        const int segment = first+start;
        for (int d=0; d<width; ++d) {
            const Z8 term = narrow(seeds+d*ntone);
            const float x = xr[segment+d], y = xi[segment+d];
            v.r += x*term.r-y*term.i;
            v.i += x*term.i+y*term.r;
        }
        for (int t=start; t<size && t<start+128; ++t) {
            const int p = first+t;
            const float scalar = norm[p];
            const F8 out_r = (v.r*scale.r-v.i*scale.i)*scalar;
            const F8 out_i = (v.r*scale.i+v.i*scale.r)*scalar;
            memcpy(ar[t], &out_r, sizeof(out_r));
            memcpy(ai[t], &out_i, sizeof(out_i));
            const F8 dr = v.r-xr[p], di = v.i-xi[p];
            const float last_r = xr[p+width], last_i = xi[p+width];
            v.r = dr*undo.r-di*undo.i+(last_r*tail.r-last_i*tail.i);
            v.i = dr*undo.i+di*undo.r+(last_r*tail.i+last_i*tail.r);
        }
    }
    transpose(ar, re, size);
    transpose(ai, im, size);
}

#define MIX(row, signs, t) (signs[0]*row[0][t]+signs[1]*row[1][t]+                \
                           signs[2]*row[2][t]+signs[3]*row[3][t]+                \
                           signs[4]*row[4][t]+signs[5]*row[5][t]+                \
                           signs[6]*row[6][t]+signs[7]*row[7][t])

#define MIX4(row, signs, t) (signs[0]*row[0][t]+signs[1]*row[1][t]+               \
                            signs[2]*row[2][t]+signs[3]*row[3][t])

static void pairs(float re[ntone][tile], float im[ntone][tile], int size,
                  float combination[4][4][2][tile]) {
    for (int j=0; j<4; ++j) {
        const float *a = re[2*j], *b = im[2*j], *c = re[2*j+1], *d = im[2*j+1];
        #pragma omp simd
        for (int t=0; t<size; ++t) {
            combination[j][0][0][t] = a[t] + c[t];
            combination[j][0][1][t] = b[t] + d[t];
            combination[j][1][0][t] = a[t] + d[t];
            combination[j][1][1][t] = b[t] - c[t];
            combination[j][2][0][t] = a[t] - c[t];
            combination[j][2][1][t] = b[t] - d[t];
            combination[j][3][0][t] = a[t] - d[t];
            combination[j][3][1][t] = b[t] + c[t];
        }
    }
}

#define FOLD(expression, correction_r, correction_i)                           \
    _Pragma("omp simd")                                                        \
    for (int t = lo; t < hi; ++t) {                                             \
        const int p = first+t;                                                  \
        const float vr = expression(r, sr, t) + (correction_r);                  \
        const float vi = expression(i, si, t) + (correction_i);                  \
        row[p-origin] += sqrtf(vr*vr+vi*vi)*energy;                              \
    }

static void accumulate(float re[ntone][tile], float im[ntone][tile],
                       const float *restrict xr, const float *restrict xi, const float *restrict norm,
                       double *restrict row, int first, int size, int limit, int epochs,
                       const int32_t *restrict starts, int anchors,
                       const int32_t *restrict offsets, int frames,
                       const uint8_t *restrict states, const Z *restrict seam,
                       const double *restrict inv_energy, int use_pairs) {
    float combination[4][4][2][tile];
    if (use_pairs) pairs(re, im, size, combination);
    for (int s = 0; s < anchors; ++s) {
        const float *r[ntone], *i[ntone];
        float sr[ntone], si[ntone];
        const int terms = use_pairs ? 4 : 8;
        for (int j = 0; j < terms; ++j) {
            const int q = states[s*ntone+(use_pairs ? 2*j : j)];
            const int rel = use_pairs ? (states[s*ntone+2*j+1]-q+4) & 3 : 0;
            const float *rv = use_pairs ? combination[j][rel][0] : re[j];
            const float *iv = use_pairs ? combination[j][rel][1] : im[j];
            r[j] = q & 1 ? iv : rv;
            i[j] = q & 1 ? rv : iv;
            sr[j] = q < 2 ? 1.0f : -1.0f;
            si[j] = q == 0 || q == 3 ? 1.0f : -1.0f;
        }
        const float dr = (float)seam[s].r, di = (float)seam[s].i;
        const float energy = (float)inv_energy[s];
        for (int frame = 0; frame < frames; ++frame) {
            const int origin = starts[s]+offsets[frame];
            if (origin >= first+size || origin >= limit) break;
            const int boundary = origin+epochs < limit ? origin+epochs : limit;
            const int lo = origin > first ? origin-first : 0;
            const int hi = boundary < first+size ? boundary-first : size;
            if (lo >= hi) continue;
            if (dr == 0 && di == 0) {
                if (use_pairs) { FOLD(MIX4, 0, 0) }
                else { FOLD(MIX, 0, 0) }
            } else {
                if (use_pairs) {
                    FOLD(MIX4, (xr[p]*dr-xi[p]*di)*norm[p], (xr[p]*di+xi[p]*dr)*norm[p])
                } else {
                    FOLD(MIX, (xr[p]*dr-xi[p]*di)*norm[p], (xr[p]*di+xi[p]*dr)*norm[p])
                }
            }
        }
    }
}

void sliding_pilot_grid(const float *restrict xr, const float *restrict xi,
                        const float *restrict norm, int limit, int epochs,
                        const int32_t *restrict starts, int anchors,
                        const int32_t *restrict offsets, int frames,
                        const uint8_t *restrict states, const Z *restrict seam,
                        const double *restrict inv_energy, const int32_t *restrict support,
                        const Z *restrict inv, const Z *restrict end, const Z *restrict coefficients,
                        const Z *restrict seeds, int frequencies, int flags,
                        double *restrict grid) {
    float re[ntone][tile], im[ntone][tile];
    memset(grid, 0, (size_t)frequencies*epochs*sizeof(*grid));
    for (int f = 0; f < frequencies; ++f) {
        double *row = grid+f*epochs;
        for (int first = 0; first < limit; first += tile) {
            const int size = limit-first < tile ? limit-first : tile;
            if (flags & 1)
                roll8(xr, xi, norm, first, size, inv+ntone*f, end+ntone*f, coefficients,
                      seeds+width*ntone*f, re, im);
            else
                roll(xr, xi, norm, first, size, inv+ntone*f, end+ntone*f, coefficients,
                     seeds+width*ntone*f, re, im);
            accumulate(re, im, xr, xi, norm, row, first, size, limit, epochs, starts, anchors,
                       offsets, frames, states, seam, inv_energy, flags & 2);
        }
        #pragma omp simd
        for (int e = 0; e < epochs; ++e)
            if (support[e]) row[e] /= support[e];
    }
}

/* Standalone drift audit over an arbitrarily long contiguous span. */
void sliding_pilot_long(const Z *restrict x, int size, const Z *restrict taps,
                        Z inv, Z end, Z *restrict out) {
    double re = 0, im = 0;
    for (int t=0; t<width; ++t) {
        re += x[t].r*taps[t].r-x[t].i*taps[t].i;
        im += x[t].r*taps[t].i+x[t].i*taps[t].r;
    }
    for (int p=0; p<=size-width; ++p) {
        out[p] = (Z){re, im};
        if (p == size-width) break;
        const double dr = re-x[p].r, di = im-x[p].i;
        const Z n = x[p+width];
        re = (dr*inv.r-di*inv.i)+(n.r*end.r-n.i*end.i);
        im = (dr*inv.i+di*inv.r)+(n.r*end.i+n.i*end.r);
    }
}
