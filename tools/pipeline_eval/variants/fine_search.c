/* Prefix of a 20,000-point binary64 forward transform for fine CFO acquisition. */
#include <math.h>
#include <stddef.h>

enum { fft_size = 20000, max_bins = 321, taps = 44 };
typedef struct { double r, i; } Complex;

static inline Complex add(Complex a, Complex b) { return (Complex){a.r+b.r, a.i+b.i}; }
static inline Complex sub(Complex a, Complex b) { return (Complex){a.r-b.r, a.i-b.i}; }
static inline Complex scale(Complex a, double b) { return (Complex){a.r*b, a.i*b}; }
static inline Complex rotate90(Complex a) { return (Complex){a.i, -a.r}; }

static inline Complex mix(Complex a, Complex b) {
    return (Complex){a.r*b.r+a.i*b.i, a.i*b.r-a.r*b.i};
}

/* PocketFFT's separable twiddle construction. Preserve each operation and sign
 * for exact agreement with the wheel's binary64 transform (BSD-3-Clause).
 * See NumPy 2.5.2, numpy/fft/pocketfft/pocketfft_hdronly.h, sincos_2pibyn.
 */
static Complex base_twiddle(int index) {
    const double angle = (double)(0.25L * 3.141592653589793238462643383279502884L / fft_size);
    int x = 8 * index;
    if (x < fft_size) return (Complex){cos(x*angle), sin(x*angle)};
    if (x < 2*fft_size) {
        double phase = (2*fft_size-x)*angle;
        return (Complex){sin(phase), cos(phase)};
    }
    if (x < 3*fft_size) {
        double phase = (x-2*fft_size)*angle;
        return (Complex){-sin(phase), cos(phase)};
    }
    double phase = (4*fft_size-x)*angle;
    return (Complex){-cos(phase), sin(phase)};
}

void fine_search_twiddles(Complex *roots) {
    Complex low[128], high[79];
    for (int i=0; i<128; ++i) low[i] = base_twiddle(i);
    for (int i=0; i<79; ++i) high[i] = base_twiddle(128*i);
    for (int i=0; i<fft_size; ++i) {
        int j = i > fft_size/2 ? fft_size-i : i;
        Complex a = low[j%128], b = high[j/128];
        double im = a.r*b.i+a.i*b.r;
        roots[i] = (Complex){a.r*b.r-a.i*b.i, i > fft_size/2 ? -im : im};
    }
}

static inline void radix8(const Complex *in, int stride, Complex out[8]) {
    const double h = 0.707106781186547524400844362104849;
    Complex o1 = add(in[stride], in[5*stride]);
    Complex o3 = add(in[3*stride], in[7*stride]);
    Complex o5 = sub(in[stride], in[5*stride]);
    Complex o7 = rotate90(sub(in[3*stride], in[7*stride]));
    Complex odd0 = add(o5, o7), odd1 = sub(o5, o7);
    Complex odd45 = {h*(odd0.r+odd0.i), h*(odd0.i-odd0.r)};
    Complex odd135 = {h*(odd1.i-odd1.r), h*(-odd1.r-odd1.i)};
    Complex e0 = add(in[0], in[4*stride]), e4 = sub(in[0], in[4*stride]);
    Complex e2 = add(in[2*stride], in[6*stride]);
    Complex e6 = rotate90(sub(in[2*stride], in[6*stride]));
    Complex a = add(e0, e2), b = add(o1, o3);
    out[0] = add(a, b);
    out[4] = sub(a, b);
    a = sub(e0, e2);
    b = rotate90(sub(o1, o3));
    out[2] = add(a, b);
    out[6] = sub(a, b);
    a = add(e4, e6);
    out[1] = add(a, odd45);
    out[5] = sub(a, odd45);
    a = sub(e4, e6);
    out[3] = add(a, odd135);
    out[7] = sub(a, odd135);
}

static inline void radix4(const Complex *in, int stride, Complex out[4]) {
    Complex a = add(in[0], in[2*stride]), b = sub(in[0], in[2*stride]);
    Complex c = add(in[stride], in[3*stride]), d = rotate90(sub(in[stride], in[3*stride]));
    out[0] = add(a, c);
    out[1] = add(b, d);
    out[2] = sub(a, c);
    out[3] = sub(b, d);
}

static inline Complex radix5_zero(const Complex *in, int width) {
    return add(add(in[0], add(in[width], in[4*width])), add(in[2*width], in[3*width]));
}

static inline void radix5(const Complex *in, int width, Complex out[5]) {
    const double c1 = 0.3090169943749474241022934171828191;
    const double c2 = -0.8090169943749474241022934171828191;
    const double s1 = -0.9510565162951535721164393333793821;
    const double s2 = -0.5877852522924731291687059546390728;
    Complex a = add(in[width], in[4*width]), b = add(in[2*width], in[3*width]);
    Complex c = sub(in[width], in[4*width]), d = sub(in[2*width], in[3*width]);
    Complex u = add(add(in[0], scale(a, c1)), scale(b, c2));
    Complex v = add(add(in[0], scale(a, c2)), scale(b, c1));
    Complex p = rotate90(scale(add(scale(c, s1), scale(d, s2)), -1.0));
    Complex q = rotate90(scale(sub(scale(c, s2), scale(d, s1)), -1.0));
    out[0] = add(add(in[0], a), b);
    out[1] = add(u, p);
    out[2] = add(v, q);
    out[3] = sub(v, q);
    out[4] = sub(u, p);
}

#define PASS(radix, previous, width, butterfly)                              \
    for (int k=0; k<previous; ++k) {                                         \
        _Pragma("omp simd")                                                  \
        for (int i=0; i<width; ++i) {                                        \
            Complex part[radix];                                            \
            butterfly(input+i+width*radix*k, width, part);                  \
            output[i+width*k] = part[0];                                    \
            for (int digit=1; digit<radix; ++digit)                          \
                output[i+width*(k+previous*digit)] =                        \
                    mix(part[digit], roots[i*previous*digit]);                \
        }                                                                    \
    }

void fine_search_transform(const Complex *restrict weighted, const Complex *restrict roots,
                           Complex *restrict work, Complex *restrict selected, int frames,
                           int bins) {
    Complex *a = work, *b = work+fft_size;
    for (int frame=0; frame<frames; ++frame) {
        /* Only even symbols 2..300 are occupied in each original frame. */
        const Complex *pilot = weighted + frame*150*taps;
        for (int j=0; j<150; ++j)
            for (int i=0; i<taps; ++i)
                a[2*(j+1)*taps+i] = pilot[j*taps+i];
        { const Complex *input=a; Complex *output=b; PASS(8, 1, 2500, radix8) }
        { const Complex *input=b; Complex *output=a; PASS(4, 8, 625, radix4) }
        { const Complex *input=a; Complex *output=b; PASS(5, 32, 125, radix5) }

        /* Frequency indexes are k + previous*digit. Once previous is 800,
         * every retained output is in digit zero of each remaining stage. */
        for (int k=0; k<bins && k<160; ++k) {
            _Pragma("omp simd")
            for (int i=0; i<25; ++i) {
                Complex part[5];
                radix5(b+i+125*k, 25, part);
                a[i+25*k] = part[0];
                if (k+160<bins) a[i+25*(k+160)] = mix(part[1], roots[i*160]);
                if (k+320<bins) a[i+25*(k+320)] = mix(part[2], roots[i*320]);
            }
        }
        for (int k=0; k<bins; ++k) {
            Complex part[5];
            for (int i=0; i<5; ++i) part[i] = radix5_zero(a+i+25*k, 5);
            selected[frame*bins+k] = radix5_zero(part, 1);
        }

        /* The second pass wrote the formerly padded entries too. */
        for (int i=0; i<fft_size; ++i) a[i] = (Complex){0, 0};
    }
}
