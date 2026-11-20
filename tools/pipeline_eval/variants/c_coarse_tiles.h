/* Included by the sealed receiver build in place of its coarse grid kernel. */
#ifndef C_COARSE_TILES_PAIR_ONLY
enum { rebase = 128 };

typedef struct {
    ToneRow carrier[tile], restore[tile];
} TileCarriers;

static void tile_carriers(TileCarriers *c) {
    const PortableFineComplex q = coefficient(0);
    for (unsigned t=0; t<tile; ++t) {
        for (unsigned j=0; j<tones; ++j) {
            const int index = (int)t*3*(2*(int)j-7);
            const double phase = tau*(index % tile)/tile;
            const double adjusted = phase+tau*tone_hz(j)*prefix_time;
            const double u = cos(adjusted), v = sin(adjusted);
            c->carrier[t].r[j] = (float)cos(phase);
            c->carrier[t].i[j] = (float)sin(phase);
            c->restore[t].r[j] = (float)((q.r*u+q.i*v)/sqrt(8.0));
            c->restore[t].i[j] = (float)((q.r*v-q.i*u)/sqrt(8.0));
        }
    }
}

static void demodulate(const PortableCoarse *w, unsigned base, unsigned size, double phase,
                       double step_r, double step_i, float *real, float *imag) {
    double cr=cos(phase*base), ci=sin(phase*base);
    for (unsigned t=0; t<size; ++t) {
        const float r=w->xr[base+t], i=w->xi[base+t];
        real[t]=(float)(r*cr-i*ci);
        imag[t]=(float)(r*ci+i*cr);
        const double next=cr*step_r-ci*step_i;
        ci=cr*step_i+ci*step_r;
        cr=next;
    }
}

/* Symmetric Qin tones share the four products with the demodulated IQ. */
static ToneRow mix_tones(float r, float i, const ToneRow *c) {
    ToneRow sample;
    #pragma omp simd
    for (unsigned j=0; j<tones/2; ++j) {
        const float rc=r*c->r[j], ic=i*c->r[j], rs=r*c->i[j], is=i*c->i[j];
        sample.r[j]=rc+is;
        sample.r[tones-1-j]=rc-is;
        sample.i[j]=ic-rs;
        sample.i[tones-1-j]=ic+rs;
    }
    return sample;
}

static void sliding(const TileCarriers *c, unsigned size, const float *xr, const float *xi,
                    float real[tones][tile], float imag[tones][tile]) {
    ToneRow stored[tile];
    for (unsigned start=0; start<size; start+=rebase) {
        ToneRow sum={{0},{0}}, ring[taps];
        for (unsigned k=0; k<taps; ++k) {
            const unsigned t=start+k;
            ring[k]=mix_tones(xr[t],xi[t],&c->carrier[t%tile]);
            #pragma omp simd
            for (unsigned j=0; j<tones; ++j) {
                sum.r[j]+=ring[k].r[j];
                sum.i[j]+=ring[k].i[j];
            }
        }
        const unsigned end=start+rebase<size ? start+rebase : size;
        unsigned head=0;
        for (unsigned t=start; t<end; ++t) {
            const ToneRow *p=&c->restore[t];
            #pragma omp simd
            for (unsigned j=0; j<tones; ++j) {
                stored[t].r[j]=sum.r[j]*p->r[j]-sum.i[j]*p->i[j];
                stored[t].i[j]=sum.r[j]*p->i[j]+sum.i[j]*p->r[j];
            }
            if (t+1==end) break;
            const unsigned k=t+taps;
            const ToneRow next=mix_tones(xr[k],xi[k],&c->carrier[k%tile]);
            #pragma omp simd
            for (unsigned j=0; j<tones; ++j) {
                sum.r[j]=(sum.r[j]-ring[head].r[j])+next.r[j];
                sum.i[j]=(sum.i[j]-ring[head].i[j])+next.i[j];
            }
            ring[head]=next;
            if (++head==taps) head=0;
        }
    }
    for (unsigned j=0; j<tones; ++j)
        for (unsigned t=0; t<size; ++t) {
            real[j][t]=stored[t].r[j];
            imag[j][t]=stored[t].i[j];
        }
}
#endif

#ifdef C_COARSE_TILES_PAIR_ONLY
enum { fold_span = 128 };
#else
enum { fold_span = tile };
#endif

static void phase_pairs(float real[tones][tile], float imag[tones][tile], unsigned shift,
                        unsigned size, float pair[4][4][2][fold_span]) {
    for (unsigned j=0; j<4; ++j) {
        const float *a=real[2*j]+shift, *b=imag[2*j]+shift;
        const float *c=real[2*j+1]+shift, *d=imag[2*j+1]+shift;
        #pragma omp simd
        for (unsigned t=0; t<size; ++t) {
            pair[j][0][0][t]=a[t]+c[t]; pair[j][0][1][t]=b[t]+d[t];
            pair[j][1][0][t]=a[t]+d[t]; pair[j][1][1][t]=b[t]-c[t];
            pair[j][2][0][t]=a[t]-c[t]; pair[j][2][1][t]=b[t]-d[t];
            pair[j][3][0][t]=a[t]-d[t]; pair[j][3][1][t]=b[t]+c[t];
        }
    }
}

#define FOLD_TILES(adj_r, adj_i)                                             \
    _Pragma("omp simd")                                                      \
    for (unsigned t=lo; t<hi; ++t) {                                         \
        const float a=signed_sum(r,sr,t)+(adj_r);                             \
        const float b=signed_sum(i,si,t)+(adj_i);                             \
        row[base+t-origin] += sqrtf(a*a+b*b)*(scale_field);                  \
    }

static inline float signed_sum(const float **part, const float *sign, unsigned t) {
    return ((part[0][t]*sign[0]+part[1][t]*sign[1])+part[2][t]*sign[2])+part[3][t]*sign[3];
}

static void fold_block(const PortableCoarse *w, const PilotAnchors *family, unsigned count,
                       unsigned limit, unsigned base, unsigned shift, unsigned size,
                       double *row, const float *xr, const float *xi,
                       float real[tones][tile], float imag[tones][tile]) {
    (void)w;
    float pair[4][4][2][fold_span];
    phase_pairs(real,imag,shift,size,pair);
    base+=shift;
    for (unsigned s=0; s<count; ++s) {
        const unsigned first=family->start[s];
        if (first>=base+size) break;
        const float *r[4], *i[4];
        float sr[4], si[4];
        for (unsigned j=0; j<4; ++j) {
            const unsigned q=family->states[s][2*j];
            const unsigned relative=(family->states[s][2*j+1]+4-q)%4;
            r[j]=pair[j][relative][q%2];
            i[j]=pair[j][relative][1-q%2];
            sr[j]=q<2 ? 1 : -1;
            si[j]=q==0 || q==3 ? 1 : -1;
        }
        const float dr=family->seam_r[s], di=family->seam_i[s];
        const float scale=family->inv_energy[s];
        #ifdef C_COARSE_TILES_PAIR_ONLY
        #define scale_field scale
        #else
        #define scale_field (scale*w->norm[base+t])
        #endif
        /* floor((40000*f+1)/3) must reach the first overlapping frame origin. */
        const unsigned earliest=base>=first+epochs ? base-first-epochs+1 : 0;
        const unsigned frame=(3*earliest+39998)/40000;
        for (unsigned f=frame; f<max_frames; ++f) {
            const unsigned origin=first+frame_offset(f);
            if (origin>=limit || origin>=base+size) break;
            const unsigned end=origin+epochs<limit ? origin+epochs : limit;
            if (end<=base) continue;
            const unsigned lo=origin>base ? origin-base : 0;
            const unsigned hi=end-base<size ? end-base : size;
            if (dr==0 && di==0) {
                FOLD_TILES(0,0)
            } else {
                #ifdef C_COARSE_TILES_PAIR_ONLY
                FOLD_TILES((xr[base+t]*dr-xi[base+t]*di)*w->norm[base+t],
                           (xr[base+t]*di+xi[base+t]*dr)*w->norm[base+t])
                #else
                FOLD_TILES(xr[t]*dr-xi[t]*di,xr[t]*di+xi[t]*dr)
                #endif
            }
        }
        #undef scale_field
    }
}

static void fold_tiles(const PortableCoarse *w, const PilotAnchors *family, unsigned count,
                       unsigned limit, unsigned base, unsigned size, double *row,
                       const float *xr, const float *xi,
                       float real[tones][tile], float imag[tones][tile]) {
    for (unsigned t=0; t<size; t+=fold_span) {
        const unsigned length=size-t<fold_span ? size-t : fold_span;
        fold_block(w,family,count,limit,base,t,length,row,xr,xi,real,imag);
    }
}

#ifndef C_COARSE_TILES_PAIR_ONLY
static void tile_row(const PortableCoarse *w, const TileCarriers *c, const PilotAnchors *family,
                     unsigned count, unsigned limit, double cfo, double *row) {
    const double phase=-tau*cfo/rate, step_r=cos(phase), step_i=sin(phase);
    for (unsigned p=0; p<limit; p+=tile) {
        const unsigned size=limit-p<tile ? limit-p : tile;
        float xr[tile+taps-1], xi[tile+taps-1];
        float real[tones][tile], imag[tones][tile];
        demodulate(w,p,size+taps-1,phase,step_r,step_i,xr,xi);
        sliding(c,size,xr,xi,real,imag);
        fold_tiles(w,family,count,limit,p,size,row,xr,xi,real,imag);
    }
}
#endif

#undef FOLD_TILES
