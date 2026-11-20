/* The qualified fine prefix FFT, vectorized across four independent frames. */
#include "fine_search.c"
#include <string.h>

typedef double Lanes __attribute__((vector_size(32)));
typedef struct { Lanes r, i; } FrameValues;

static inline FrameValues plus(FrameValues a, FrameValues b) {
    return (FrameValues){a.r+b.r, a.i+b.i};
}

static inline FrameValues minus(FrameValues a, FrameValues b) {
    return (FrameValues){a.r-b.r, a.i-b.i};
}

static inline FrameValues times(FrameValues a, double b) {
    return (FrameValues){a.r*b, a.i*b};
}

static inline FrameValues turn(FrameValues a) { return (FrameValues){a.i, -a.r}; }

static inline FrameValues twiddled(FrameValues a, Complex b) {
    return (FrameValues){a.r*b.r+a.i*b.i, a.i*b.r-a.r*b.i};
}

static inline void butterflies8(const FrameValues *x, int s, FrameValues out[8]) {
    const double h = 0.707106781186547524400844362104849;
    FrameValues odd_a = plus(x[s], x[5*s]), odd_b = plus(x[3*s], x[7*s]);
    FrameValues odd_c = minus(x[s], x[5*s]), odd_d = turn(minus(x[3*s], x[7*s]));
    FrameValues c = plus(odd_c, odd_d), d = minus(odd_c, odd_d);
    FrameValues at45 = {h*(c.r+c.i), h*(c.i-c.r)}, at135 = {h*(d.i-d.r), h*(-d.r-d.i)};
    FrameValues even_a = plus(x[0], x[4*s]), even_b = plus(x[2*s], x[6*s]);
    FrameValues even_c = minus(x[0], x[4*s]), even_d = turn(minus(x[2*s], x[6*s]));
    FrameValues a = plus(even_a, even_b), b = plus(odd_a, odd_b);
    out[0] = plus(a, b);
    out[4] = minus(a, b);
    a = minus(even_a, even_b);
    b = turn(minus(odd_a, odd_b));
    out[2] = plus(a, b);
    out[6] = minus(a, b);
    a = plus(even_c, even_d);
    out[1] = plus(a, at45);
    out[5] = minus(a, at45);
    a = minus(even_c, even_d);
    out[3] = plus(a, at135);
    out[7] = minus(a, at135);
}

static inline void butterflies4(const FrameValues *x, int s, FrameValues out[4]) {
    FrameValues a = plus(x[0], x[2*s]), b = minus(x[0], x[2*s]);
    FrameValues c = plus(x[s], x[3*s]), d = turn(minus(x[s], x[3*s]));
    out[0] = plus(a, c);
    out[1] = plus(b, d);
    out[2] = minus(a, c);
    out[3] = minus(b, d);
}

static inline FrameValues dc5(const FrameValues *x, int s) {
    return plus(plus(x[0], plus(x[s], x[4*s])), plus(x[2*s], x[3*s]));
}

static inline void butterflies5(const FrameValues *x, int s, FrameValues out[5]) {
    const double c1 = 0.3090169943749474241022934171828191;
    const double c2 = -0.8090169943749474241022934171828191;
    const double s1 = -0.9510565162951535721164393333793821;
    const double s2 = -0.5877852522924731291687059546390728;
    FrameValues a = plus(x[s], x[4*s]), b = plus(x[2*s], x[3*s]);
    FrameValues c = minus(x[s], x[4*s]), d = minus(x[2*s], x[3*s]);
    FrameValues u = plus(plus(x[0], times(a, c1)), times(b, c2));
    FrameValues v = plus(plus(x[0], times(a, c2)), times(b, c1));
    FrameValues p = turn(times(plus(times(c, s1), times(d, s2)), -1.0));
    FrameValues q = turn(times(minus(times(c, s2), times(d, s1)), -1.0));
    out[0] = plus(plus(x[0], a), b);
    out[1] = plus(u, p);
    out[2] = plus(v, q);
    out[3] = minus(v, q);
    out[4] = minus(u, p);
}

#define FRAME_PASS(radix, previous, width)                                \
    for (int k=0; k<previous; ++k) {                                      \
        for (int i=0; i<width; ++i) {                                     \
            FrameValues part[radix];                                       \
            butterflies##radix(input+i+width*radix*k, width, part);       \
            output[i+width*k] = part[0];                                  \
            for (int digit=1; digit<radix; ++digit)                        \
                output[i+width*(k+previous*digit)] =                      \
                    twiddled(part[digit], roots[i*previous*digit]);       \
        }                                                                 \
    }

void fine_batch_transform(const Complex *restrict weighted, const Complex *restrict roots,
                          FrameValues *restrict work, Complex *restrict selected, int frames,
                          int bins) {
    FrameValues *a = work, *b = work + fft_size;
    for (int frame=0; frame<frames; frame+=4) {
        const Complex *x[4];
        int lanes = frames-frame < 4 ? frames-frame : 4;
        for (int q=0; q<4; ++q)
            x[q] = weighted + (frame + (q < lanes ? q : 0))*150*taps;
        memset(a, 0, fft_size*sizeof(*a));
        for (int j=0; j<150; ++j) {
            for (int i=0; i<taps; ++i) {
                int p = j*taps+i;
                a[2*(j+1)*taps+i] = (FrameValues){
                    {x[0][p].r, x[1][p].r, x[2][p].r, x[3][p].r},
                    {x[0][p].i, x[1][p].i, x[2][p].i, x[3][p].i}
                };
            }
        }
        { const FrameValues *input=a; FrameValues *output=b; FRAME_PASS(8, 1, 2500) }
        { const FrameValues *input=b; FrameValues *output=a; FRAME_PASS(4, 8, 625) }
        { const FrameValues *input=a; FrameValues *output=b; FRAME_PASS(5, 32, 125) }
        for (int k=0; k<bins && k<160; ++k) {
            for (int i=0; i<25; ++i) {
                FrameValues part[5];
                butterflies5(b+i+125*k, 25, part);
                a[i+25*k] = part[0];
                if (k+160<bins) a[i+25*(k+160)] = twiddled(part[1], roots[i*160]);
                if (k+320<bins) a[i+25*(k+320)] = twiddled(part[2], roots[i*320]);
            }
        }
        for (int k=0; k<bins; ++k) {
            FrameValues part[5];
            for (int i=0; i<5; ++i) part[i] = dc5(a+i+25*k, 5);
            FrameValues bin = dc5(part, 1);
            for (int q=0; q<lanes; ++q)
                selected[(frame+q)*bins+k] = (Complex){bin.r[q], bin.i[q]};
        }
    }
}
