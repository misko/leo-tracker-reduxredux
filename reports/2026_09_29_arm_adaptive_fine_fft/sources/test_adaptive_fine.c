static int regional_count;
static int regional_epochs[13334];
#include "full_search.c"
#include <assert.h>
#include <stdio.h>

static void classifier(void)
{
    double strong[11]={0}; strong[5]=10; strong[1]=2;
    double ambiguous[11]={0}; ambiguous[2]=10; ambiguous[8]=9;
    double neighbor[11]={0}; neighbor[5]=10; neighbor[6]=9;
    double flat[11]={0};
    assert(leo_fine_dominant(strong,11));
    assert(!leo_fine_dominant(ambiguous,11));
    assert(leo_fine_dominant(neighbor,11));
    assert(!leo_fine_dominant(flat,11));
}

static void fill_tones(leo_presence_complex *samples,size_t count,uint32_t rate,
    double f1,double a1,double f2,double a2)
{
    for(size_t k=0;k<count;k++) {
        double p1=2*acos(-1.0)*f1*k/rate,p2=2*acos(-1.0)*f2*k/rate;
        samples[k]=(leo_presence_complex){a1*cos(p1)+a2*cos(p2),
            a1*sin(p1)+a2*sin(p2)};
    }
}

static void rate(uint32_t rate)
{
    size_t n=(rate+375)/750,count=rate/50;
    leo_presence_complex *exact=calloc(n,sizeof(*exact));
    leo_presence_complex *control=calloc(n,sizeof(*control));
    leo_presence_complex *samples=calloc(count,sizeof(*samples));
    assert(exact&&control&&samples);
    for(size_t k=0;k<n;k++) exact[k]=(leo_presence_complex){1,0};
    leo_presence_workspace *w=leo_presence_create(rate,exact,control,n);
    assert(w); w->acquisition_first_frame=0;
    double scores[129]; leo_fine_precision_cache c;

    fill_tones(samples,count,rate,7000,1,0,0);
    assert(!ingest(w,samples,count)&&!leo_fine_precision_init(&c,w->fine_fft.size));
    assert(!leo_fine_precision_scores(w,count,(int)n/4,-32000,129,scores,&c));
    assert(c.transforms==1&&c.first_only==1&&c.second_computed==0);
    leo_fine_precision_free(&c);

    fill_tones(samples,count,rate,-9000,1,11000,1);
    assert(!ingest(w,samples,count)&&!leo_fine_precision_init(&c,w->fine_fft.size));
    /* A narrow first request sees only one peak. A later wider request for
     * the cached epoch must still be allowed to trigger endpoint two. */
    assert(!leo_fine_precision_scores(w,count,(int)n/4,-11000,9,scores,&c));
    assert(c.transforms==1&&c.first_only==1);
    assert(!leo_fine_precision_scores(w,count,(int)n/4,-32000,129,scores,&c));
    assert(c.transforms==2&&c.second_computed==1&&c.hits==1);
    leo_fine_precision_free(&c);

    count=(size_t)ceil(rate/375.0);
    fill_tones(samples,count,rate,7000,1,0,0);
    assert(!ingest(w,samples,count)&&!leo_fine_precision_init(&c,w->fine_fft.size));
    assert(!leo_fine_precision_scores(w,count,0,-32000,129,scores,&c));
    assert(c.entries[0].available<LEO_PRESENCE_FINE_FRAMES&&c.transforms==1&&
        !c.entries[0].computed[1]&&c.first_only==1);
    leo_fine_precision_free(&c); leo_presence_destroy(w);
    free(samples); free(control); free(exact);
}

int main(void)
{
    classifier();
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int i=0;i<4;i++) rate(rates[i]);
    puts("adaptive fine FFT: strong tone, ambiguous two-tone, lazy range, partial input, all rates ok");
    return 0;
}
