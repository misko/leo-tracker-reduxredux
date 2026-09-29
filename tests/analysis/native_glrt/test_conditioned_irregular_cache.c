/* Bitwise differential test for cached clipped-grid rotations. */
static int regional_count;
static int regional_epochs[13334];
#include "../../../src/leo/analysis/native_glrt/kernel/private/full_search.c"
#include <assert.h>

static void dot_trial(size_t n)
{
    float *a=malloc(2*n*sizeof(*a)),*b=malloc(8*n*sizeof(*b));assert(a&&b);
    for(size_t k=0;k<2*n;++k)a[k]=(float)((int)(k%29)-14)/17.0f;
    for(size_t k=0;k<8*n;++k)b[k]=(float)((int)(k%31)-15)/19.0f;
    double complex tiled[4];full_blocked_dots_four(a,b,n,tiled);
    for(int f=0;f<4;++f)
        assert(!memcmp(&tiled[f],&(double complex){full_blocked_dot(a,b+2*(size_t)f*n,n)},
            sizeof(tiled[f])));
    free(b);free(a);
}

static void reference_scores(leo_presence_workspace *w,size_t count,int epoch,
    const double *frequencies,int nf,double *scores,int approximate)
{
    double te=0;memset(scores,0,(size_t)nf*sizeof(*scores));
    int block_screen=approximate&&nf>0&&nf<=64;
    for(int f=0;f<nf&&block_screen;++f)
        block_screen=frequencies[f]==frequencies[0]+f*100.0;
    double complex basis[32],anchor=1;
    if(block_screen)for(size_t j=0;j<32;++j)basis[j]=rotate(-TAU*frequencies[0]*j/w->rate);
    for(size_t k=0;k<w->n;++k){te+=power(w->exact[k]);if(block_screen){if(!(k&31))anchor=rotate(-TAU*frequencies[0]*k/w->rate);w->base[k]=conj(w->exact[k])*(anchor*basis[k&31]);}else w->base[k]=conj(w->exact[k])*rotate(-TAU*frequencies[0]*k/w->rate);}
    int frames=0;
    for(int frame=0;frame<16;++frame){int start=frame_start(w,epoch,frame);if((size_t)start+w->n>count)break;double energy=0;for(size_t k=0;k<w->n;++k){energy+=power(w->samples[start+k]);w->weighted[k]=w->samples[start+k]*w->base[k];if(approximate){w->opt_weighted[2*k]=(float)creal(w->weighted[k]);w->opt_weighted[2*k+1]=(float)cimag(w->weighted[k]);}}double denom=sqrt(te*energy);float moment_magnitudes[64];int regular=nf>0&&nf<=64;for(int f=0;f<nf&&regular;++f)regular=frequencies[f]==frequencies[0]+f*100.0;int moment_ok=approximate&&denom>0&&regular;if(moment_ok)moment_ok=!conditioned_moment_magnitudes(w->opt_weighted,w->n,w->rate,nf,moment_magnitudes);for(int f=0;f<nf&&denom>0;++f){double complex total=0;int bin_regular=frequencies[f]==frequencies[0]+f*100.0;if(moment_ok){scores[f]+=moment_magnitudes[f]/denom;continue;}else if(approximate&&bin_regular)total=full_blocked_dot(w->opt_weighted,w->opt_conditioned_offsets+2*f*w->n,w->n);else for(size_t k=0;k<w->n;++k)total+=w->weighted[k]*(bin_regular?w->conditioned_offsets[f*w->n+k]:rotate(-TAU*(frequencies[f]-frequencies[0])*k/w->rate));scores[f]+=magnitude(total)/denom;}++frames;}if(frames)for(int f=0;f<nf;++f)scores[f]/=frames;
}

static void trial(uint32_t rate,int supported_frames,int zero)
{
    size_t n=(size_t)nearbyint(rate/750.0),count=n+(size_t)(supported_frames-1)*n;
    leo_presence_complex *t=calloc(n,sizeof(*t));assert(t);
    for(size_t k=0;k<n;++k){t[k].re=cos(.013*k);t[k].im=sin(.013*k);}
    leo_presence_workspace *w=leo_presence_create(rate,t,t,n);free(t);assert(w);
    if(count>w->max_samples)count=w->max_samples;
    for(size_t k=0;k<count;++k)w->samples[k]=zero?0:cos(.017*k)+I*sin(.017*k);
    double frequencies[32],a[32],b[32];int nf=grid(-400000,-397650,100,frequencies);
    assert(nf==25&&frequencies[nf-2]==-397700&&frequencies[nf-1]==-397650);
    reference_scores(w,count,0,frequencies,nf,a,1);
    full_conditioned_scores(w,count,0,frequencies,nf,b,1);
    assert(!memcmp(a,b,(size_t)nf*sizeof(*a)));
    leo_presence_destroy(w);
}

int main(void)
{
    const size_t dot_lengths[]={1,63,64,65,3333,6667,10000,13333};
    for(size_t n=0;n<sizeof(dot_lengths)/sizeof(*dot_lengths);++n)dot_trial(dot_lengths[n]);
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t r=0;r<4;++r){trial(rates[r],16,0);trial(rates[r],3,0);trial(rates[r],4,1);}
    return 0;
}
