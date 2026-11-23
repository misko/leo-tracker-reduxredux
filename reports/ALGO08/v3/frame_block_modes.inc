/* Two phase-aligned native frame pairs, leaving the exact downstream verifier intact. */
#include <stdint.h>
#include <time.h>

typedef struct {
    int count;
    int epoch[4];
    double signed_hz[4];
    uint64_t proposal_ns;
} FrameBlockTrace;

static _Thread_local FrameBlockTrace block_trace;

void frame_block_read(FrameBlockTrace *out) { *out = block_trace; }

static uint64_t block_cpu_now(void) {
    struct timespec now;
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &now);
    return (uint64_t)now.tv_sec * 1000000000 + (uint64_t)now.tv_nsec;
}

static void coherent_frame_pairs(TimingFirst *w, const Sample *low) {
    const int pairs[2] = {0, 6};
    const int count = w->width;
    for (int pair = 0; pair < 2; ++pair) {
        const Sample *a = low + rounded_offset(pairs[pair], w->stride) + first/w->stride;
        const Sample *b = low + rounded_offset(pairs[pair]+1, w->stride) + first/w->stride;
        double ar = 0., ai = 0., br = 0., bi = 0.;
        double aa = 0., bb = 0., re = 0., im = 0.;
        for (int j = 0; j < count; ++j) {
            double xr = a[j].re, xi = a[j].im, yr = b[j].re, yi = b[j].im;
            ar += xr;
            ai += xi;
            br += yr;
            bi += yi;
            aa += xr*xr + xi*xi;
            bb += yr*yr + yi*yi;
            re += xr*yr + xi*yi;
            im += xi*yr - xr*yi;
        }
        re -= (ar*br + ai*bi)/count;
        im -= (ai*br - ar*bi)/count;
        double norm = hypot(re, im);
        Sample phase = norm > 0 ? (Sample){re/norm, im/norm} : (Sample){1.f, 0.f};
        float left = 1./fmax(sqrt(fmax(0., aa/count-(ar*ar+ai*ai)/(count*(double)count))), 1e-12);
        float right = 1./fmax(sqrt(fmax(0., bb/count-(br*br+bi*bi)/(count*(double)count))), 1e-12);
        const Sample av = {(float)(ar/count), (float)(ai/count)};
        const Sample bv = {(float)(br/count), (float)(bi/count)};
        Sample *out = w->modes + pair*count;
        for (int j = 0; j < count; ++j) {
            Sample y = {(b[j].re-bv.re)*right, (b[j].im-bv.im)*right};
            Sample z = multiply(phase, y);
            out[j] = (Sample){(a[j].re-av.re)*left+z.re, (a[j].im-av.im)*left+z.im};
        }
    }
}
