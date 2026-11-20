/* Fixed-geometry original Qin coarse acquisition. Requires only the C math library. */
#include "portable_coarse.h"
#include "portable_coarse_qin.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

enum { samples = PORTABLE_FINE_SAMPLES, epochs = PORTABLE_FINE_EPOCHS, taps = 44,
       lanes = PORTABLE_COARSE_MAX_LANES, tile = 256, tones = 8, max_frames = 15 };
static const double tau = 6.283185307179586476925286766559;
static const double rate = 10e6;
static const double duration = 4.4e-6;
static const double prefix_time = (2.0/15.0)*1e-6;

typedef struct { float r[tones], i[tones]; } ToneRow;
typedef struct {
    unsigned start[22];
    uint8_t states[22][tones];
    float seam_r[22], seam_i[22], inv_energy[22];
} PilotAnchors;

struct PortableCoarse {
    unsigned edge, last_lanes;
    PortableFineComplex exact[epochs], control[epochs];
    PilotAnchors family[2];
    float xr[samples+1], xi[samples+1], norm[samples-taps+1];
    double grid[lanes*epochs];
    uint8_t eligible[lanes*epochs];
    uint16_t support[epochs];
};

static double tone_hz(unsigned j) { return (2*(int)j-7)*117187.5; }
static unsigned frame_offset(unsigned frame) { return (40000*frame+1)/3; }

static uint8_t state(unsigned edge, unsigned tone, unsigned row) {
    unsigned c = (unsigned)portable_coarse_qin[edge][tone][row/2];
    unsigned nibble = c >= 'A' ? c-'A'+10 : c-'0';
    return (uint8_t)((nibble >> (row%2 ? 0 : 2)) & 3);
}

static PortableFineComplex coefficient(unsigned q) {
    const double a = (double)0.70710678118654752440084436210f;
    return (PortableFineComplex){q == 0 || q == 3 ? a : -a, q < 2 ? a : -a};
}

static PortableFineComplex ideal(unsigned edge, unsigned row, double local) {
    PortableFineComplex value = {0,0};
    for (unsigned j=0; j<tones; ++j) {
        const PortableFineComplex c = coefficient(state(edge, j, row));
        const double phase = (tau*tone_hz(j))*(local-prefix_time);
        const double u = cos(phase), v = sin(phase);
        value.r += c.r*u-c.i*v;
        value.i += c.r*v+c.i*u;
    }
    return (PortableFineComplex){value.r/sqrt(8.0), value.i/sqrt(8.0)};
}

static void templates(PortableFineComplex *exact, PortableFineComplex *control, unsigned edge) {
    for (unsigned p=0; p<epochs; ++p) {
        const double time = p/rate;
        const unsigned s = (unsigned)floor(time/duration);
        if (s < 2 || s > 301) continue;
        const double local = time-s*duration;
        PortableFineComplex primary = ideal(edge, s-2, local);
        PortableFineComplex rotated = ideal(edge, (s-2+300-17)%300, local);
        exact[p] = (PortableFineComplex){(float)primary.r, (float)primary.i};
        control[p] = (PortableFineComplex){(float)rotated.r, (float)rotated.i};
    }
}

static void anchors(PortableCoarse *w, PilotAnchors *family, unsigned count, unsigned step) {
    for (unsigned s=0; s<count; ++s) {
        const unsigned symbol = 2+step*s, p = taps*symbol;
        family->start[s] = p;
        for (unsigned j=0; j<tones; ++j) family->states[s][j] = state(w->edge,j,symbol-2);
        const PortableFineComplex expected = ideal(w->edge,symbol-2,0);
        const double dr = w->exact[p].r-expected.r, di = expected.i-w->exact[p].i;
        if (hypot(dr,di)>1e-7) {
            family->seam_r[s] = (float)dr;
            family->seam_i[s] = (float)di;
        }
        double energy = 0;
        for (unsigned j=0; j<taps; ++j) {
            PortableFineComplex x = w->exact[p+j];
            energy += x.r*x.r+x.i*x.i;
        }
        family->inv_energy[s] = (float)(1/sqrt(energy));
    }
}

PortableCoarse *portable_coarse_create(unsigned edge) {
    if (edge > PORTABLE_COARSE_UPPER) return NULL;
    PortableCoarse *w = calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->edge = edge;
    templates(w->exact,w->control,edge);
    anchors(w,&w->family[0],PORTABLE_COARSE_PRIMARY,26);
    anchors(w,&w->family[1],PORTABLE_COARSE_RETRY,14);
    return w;
}

void portable_coarse_free(PortableCoarse *w) { free(w); }
size_t portable_coarse_workspace_bytes(void) { return sizeof(PortableCoarse); }

const PortableFineComplex *portable_coarse_template(const PortableCoarse *w, unsigned control) {
    if (!w || control > 1) return NULL;
    return control ? w->control : w->exact;
}

const double *portable_coarse_scores(const PortableCoarse *w, unsigned *lane_count) {
    if (!w || !lane_count) return NULL;
    *lane_count = w->last_lanes;
    return w->grid;
}

const uint16_t *portable_coarse_support(const PortableCoarse *w) {
    return w ? w->support : NULL;
}

static unsigned best_enabled(const double *row, const uint8_t *eligible, unsigned count) {
    unsigned best = count;
    for (unsigned e=0; e<count; ++e)
        if (eligible[e] && (best==count || row[e]>row[best])) best=e;
    return best;
}

static int better(double a, double b, double fa, double fb, unsigned ea, unsigned eb) {
    if (a != b) return a > b;
    if (fabs(fa) != fabs(fb)) return fabs(fa) < fabs(fb);
    return ea < eb;
}

unsigned portable_coarse_select(const double *grid, const double *residual, unsigned rows,
                                unsigned count, uint8_t *eligible, PortableCoarsePeak *peaks) {
    if (!grid || !residual || !eligible || !peaks || rows<1 || rows>lanes || count<1 ||
        count>epochs) return 0;
    unsigned best[lanes];
    for (unsigned f=0; f<rows; ++f) {
        const double *row = grid+f*count;
        uint8_t *valid = eligible+f*count;
        for (unsigned e=0; e<count; ++e) {
            const double left = e ? row[e-1] : -INFINITY;
            const double right = e+1<count ? row[e+1] : -INFINITY;
            valid[e] = count==1 ? row[e]>0
                               : row[e]>=left && row[e]>=right && (row[e]>left || row[e]>right);
        }
        best[f] = best_enabled(row,valid,count);
    }
    unsigned retained = 0;
    for (; retained<PORTABLE_VERIFIER_MAX_SEEDS; ++retained) {
        unsigned f = rows;
        for (unsigned j=0; j<rows; ++j) {
            if (best[j]==count) continue;
            if (f==rows || better(grid[j*count+best[j]],grid[f*count+best[f]],
                                   residual[j],residual[f],best[j],best[f])) f=j;
        }
        if (f==rows) break;
        const unsigned e = best[f];
        const double *row = grid+f*count;
        if (retained==0 && row[e]<=0) break;
        const unsigned lo = e ? e-1 : 0, hi = e+1<count ? e+1 : e;
        unsigned refined = lo;
        for (unsigned j=lo+1; j<=hi; ++j)
            if (row[j]>row[refined]) refined=j;
        peaks[retained] = (PortableCoarsePeak){row[e],residual[f],e,refined,f};
        for (unsigned j=0; j<rows; ++j) {
            if (fabs(residual[j]-residual[f])>10000.0) continue;
            uint8_t *valid = eligible+j*count;
            for (int d=-4; d<=4; ++d) {
                const unsigned q = (unsigned)(((int)e+d)%(int)count+(int)count)%count;
                valid[q] = 0;
            }
            if (best[j] < count && !valid[best[j]])
                best[j] = best_enabled(grid+j*count,valid,count);
        }
    }
    return retained;
}

static float norm(double energy) { return energy > 0 ? (float)(1/sqrt(energy)) : 0; }

static void load(PortableCoarse *w, const int16_t *iq, unsigned n, unsigned lane) {
    double energy = 0;
    for (unsigned p=0; p<n; ++p) {
        const double r = iq[4*p+2*lane], i = iq[4*p+2*lane+1];
        w->xr[p] = (float)r;
        w->xi[p] = (float)i;
        energy += r*r+i*i;
        if (p>=taps) {
            const double old_r=w->xr[p-taps], old_i=w->xi[p-taps];
            energy -= old_r*old_r+old_i*old_i;
        }
        if (p+1>=taps) w->norm[p+1-taps] = norm(energy);
    }
    w->xr[n] = w->xi[n] = 0;
}

static void rotations(double cfo, ToneRow *seed, ToneRow *undo, ToneRow *tail, ToneRow *amp) {
    PortableFineComplex q = coefficient(0);
    for (unsigned j=0; j<tones; ++j) {
        const double phase = -tau*(cfo+tone_hz(j))/rate;
        const double p = -tau*tone_hz(j)*prefix_time;
        const double c = cos(p), s = sin(p);
        amp->r[j] = (float)((q.r*c-q.i*s)/sqrt(8.0));
        amp->i[j] = (float)(-(q.r*s+q.i*c)/sqrt(8.0));
        undo->r[j] = (float)cos(-phase);
        undo->i[j] = (float)sin(-phase);
        tail->r[j] = (float)cos(43*phase);
        tail->i[j] = (float)sin(43*phase);
        for (unsigned t=0; t<taps; ++t) {
            seed[t].r[j] = (float)cos(t*phase);
            seed[t].i[j] = (float)sin(t*phase);
        }
    }
}

static void roll(const PortableCoarse *w, unsigned base, unsigned size,
                 const ToneRow *seed, ToneRow undo, ToneRow tail, ToneRow amp,
                 float real[tones][tile], float imag[tones][tile]) {
    ToneRow stored[tile];
    for (unsigned segment=0; segment<size; segment+=128) {
        ToneRow v = {{0},{0}};
        for (unsigned t=0; t<taps; ++t) {
            const unsigned p=base+segment+t;
            const float r=w->xr[p], i=w->xi[p];
            #pragma omp simd
            for (unsigned j=0; j<tones; ++j) {
                v.r[j] += r*seed[t].r[j]-i*seed[t].i[j];
                v.i[j] += r*seed[t].i[j]+i*seed[t].r[j];
            }
        }
        const unsigned end = segment+128<size ? segment+128 : size;
        for (unsigned t=segment; t<end; ++t) {
            const unsigned p=base+t;
            const float n=w->norm[p], r=w->xr[p], i=w->xi[p];
            const float nr=w->xr[p+taps], ni=w->xi[p+taps];
            #pragma omp simd
            for (unsigned j=0; j<tones; ++j) {
                const float a=v.r[j]-r, b=v.i[j]-i;
                stored[t].r[j] = (v.r[j]*amp.r[j]-v.i[j]*amp.i[j])*n;
                stored[t].i[j] = (v.r[j]*amp.i[j]+v.i[j]*amp.r[j])*n;
                v.r[j] = a*undo.r[j]-b*undo.i[j]+(nr*tail.r[j]-ni*tail.i[j]);
                v.i[j] = a*undo.i[j]+b*undo.r[j]+(nr*tail.i[j]+ni*tail.r[j]);
            }
        }
    }
    for (unsigned j=0; j<tones; ++j)
        for (unsigned t=0; t<size; ++t) {
            real[j][t] = stored[t].r[j];
            imag[j][t] = stored[t].i[j];
        }
}

static void phase_pairs(float real[tones][tile], float imag[tones][tile], unsigned size,
                        float pair[4][4][2][tile]) {
    for (unsigned j=0; j<4; ++j) {
        const float *a=real[2*j], *b=imag[2*j], *c=real[2*j+1], *d=imag[2*j+1];
        #pragma omp simd
        for (unsigned t=0; t<size; ++t) {
            pair[j][0][0][t]=a[t]+c[t]; pair[j][0][1][t]=b[t]+d[t];
            pair[j][1][0][t]=a[t]+d[t]; pair[j][1][1][t]=b[t]-c[t];
            pair[j][2][0][t]=a[t]-c[t]; pair[j][2][1][t]=b[t]-d[t];
            pair[j][3][0][t]=a[t]-d[t]; pair[j][3][1][t]=b[t]+c[t];
        }
    }
}

#define FIRST4(z,s,t) (s[0]*z[0][t]+s[1]*z[1][t]+s[2]*z[2][t]+s[3]*z[3][t])
#define ALL8(z,s,t) (FIRST4(z,s,t)+s[4]*z[4][t]+s[5]*z[5][t]+s[6]*z[6][t]+s[7]*z[7][t])
#define FOLD(sum, adj_r, adj_i)                                              \
    _Pragma("omp simd")                                                       \
    for (unsigned t=lo; t<hi; ++t) {                                         \
        const unsigned p=base+t;                                            \
        const float a=sum(r,sr,t)+(adj_r), b=sum(i,si,t)+(adj_i);            \
        row[p-origin] += sqrtf(a*a+b*b)*family->inv_energy[s];                \
    }

static void fold(const PortableCoarse *w, const PilotAnchors *family, unsigned count,
                 unsigned limit, unsigned base, unsigned size, double *row,
                 float real[tones][tile], float imag[tones][tile]) {
    const int shared = count==PORTABLE_COARSE_RETRY;
    float pair[4][4][2][tile];
    if (shared) phase_pairs(real,imag,size,pair);
    for (unsigned s=0; s<count; ++s) {
        const float *r[tones], *i[tones];
        float sr[tones], si[tones];
        for (unsigned j=0; j<(shared ? 4u : 8u); ++j) {
            const unsigned q=family->states[s][shared ? 2*j : j];
            const unsigned relative=shared ? (family->states[s][2*j+1]+4-q)%4 : 0;
            const float *re=shared ? pair[j][relative][0] : real[j];
            const float *im=shared ? pair[j][relative][1] : imag[j];
            r[j] = q%2 ? im : re;
            i[j] = q%2 ? re : im;
            sr[j] = q<2 ? 1 : -1;
            si[j] = q==0 || q==3 ? 1 : -1;
        }
        const float dr=family->seam_r[s], di=family->seam_i[s];
        for (unsigned f=0; f<max_frames; ++f) {
            const unsigned origin=family->start[s]+frame_offset(f);
            if (origin>=limit || origin>=base+size) break;
            const unsigned end=origin+epochs<limit ? origin+epochs : limit;
            if (end<=base) continue;
            const unsigned lo=origin>base ? origin-base : 0;
            const unsigned hi=end-base<size ? end-base : size;
            if (dr==0 && di==0) {
                if (shared) { FOLD(FIRST4,0,0) }
                else { FOLD(ALL8,0,0) }
            } else if (shared) {
                FOLD(FIRST4,(w->xr[p]*dr-w->xi[p]*di)*w->norm[p],
                     (w->xr[p]*di+w->xi[p]*dr)*w->norm[p])
            } else {
                FOLD(ALL8,(w->xr[p]*dr-w->xi[p]*di)*w->norm[p],
                     (w->xr[p]*di+w->xi[p]*dr)*w->norm[p])
            }
        }
    }
}

static void grid(PortableCoarse *w, const PilotAnchors *family, unsigned n, unsigned count,
                 const double *residual, double center, unsigned rows) {
    const unsigned limit=n-taps+1;
    memset(w->support,0,sizeof(w->support));
    for (unsigned s=0; s<count; ++s) {
        for (unsigned f=0; f<max_frames; ++f) {
            const unsigned origin=family->start[s]+frame_offset(f);
            if (origin>=limit) break;
            const unsigned end=limit-origin<epochs ? limit-origin : epochs;
            for (unsigned e=0; e<end; ++e) ++w->support[e];
        }
    }
    float real[tones][tile], imag[tones][tile];
    for (unsigned f=0; f<rows; ++f) {
        ToneRow seed[taps], undo, tail, amp;
        rotations(center+residual[f],seed,&undo,&tail,&amp);
        double *row=w->grid+f*epochs;
        memset(row,0,epochs*sizeof(*row));
        for (unsigned p=0; p<limit; p+=tile) {
            const unsigned size=limit-p<tile ? limit-p : tile;
            roll(w,p,size,seed,undo,tail,amp,real,imag);
            fold(w,family,count,limit,p,size,row,real,imag);
        }
        for (unsigned e=0; e<epochs; ++e)
            if (w->support[e]) row[e]/=w->support[e];
    }
}

int portable_coarse_acquire(PortableCoarse *w, const int16_t *iq,
                            const PortableCoarseCapture *cap, unsigned lane, unsigned count,
                            PortableVerifierSeed *seeds, PortableCoarsePeak *peaks,
                            unsigned *retained) {
    if (!retained) return -1;
    *retained=0;
    if (!w || !iq || !cap || !seeds || lane>=2 || cap->lane_mask>3 || cap->samples>samples ||
        cap->edge!=w->edge || (count!=PORTABLE_COARSE_PRIMARY && count!=PORTABLE_COARSE_RETRY))
        return -1;
    w->last_lanes=0;
    memset(w->support,0,sizeof(w->support));
    if (!(cap->lane_mask&(1u<<lane)) || cap->samples<302*taps+epochs) return 0;
    const double width=cap->high_hz-cap->low_hz, center=cap->center_hz[lane];
    if (!isfinite(center) || !isfinite(cap->low_hz) || !isfinite(cap->high_hz) ||
        width<80000 || width>1600000 || fmod(width,80000)!=0 ||
        fmax(fabs(center+cap->low_hz),fabs(center+cap->high_hz))>rate/2) return -1;
    double residual[lanes];
    const unsigned rows=1+(unsigned)(width/80000);
    for (unsigned f=0; f<rows; ++f) residual[f]=cap->low_hz+80000*f;
    load(w,iq,cap->samples,lane);
    grid(w,&w->family[count==PORTABLE_COARSE_RETRY],cap->samples,count,residual,center,rows);
    w->last_lanes=rows;
    PortableCoarsePeak local[PORTABLE_VERIFIER_MAX_SEEDS];
    if (!peaks) peaks=local;
    *retained=portable_coarse_select(w->grid,residual,rows,epochs,w->eligible,peaks);
    for (unsigned i=0; i<*retained; ++i) {
        const double low=fmax(cap->low_hz,peaks[i].residual_hz-80000);
        const double high=fmin(cap->high_hz,peaks[i].residual_hz+80000);
        seeds[i]=(PortableVerifierSeed){
            peaks[i].refined_epoch, 1+(unsigned)((high-low)/500), center+low, low
        };
    }
    return 0;
}
