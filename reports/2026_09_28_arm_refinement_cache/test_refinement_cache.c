#include "full_search.c"
#include <assert.h>
#include <float.h>
#include <stdint.h>
#include <stdio.h>

static void key_tests(uint32_t rate)
{
    for(int window=0;window<2;++window) {
        refinement_cache_entry refinement[LEO_FULL_SEARCH_MAX_CANDIDATES];int nr=0;
        glrt_cache_entry final[LEO_FULL_SEARCH_MAX_CANDIDATES];int ng=0;
        double lower=-2000.0+rate*0.0,cfo=12345.25;
        double last=2000.0;
        assert(refinement_cache_find(refinement,nr,17,lower,last,41)<0);
        refinement[nr++]=(refinement_cache_entry){17,41,lower,last,cfo,.25,{.5,.6,.7}};
        int i=refinement_cache_find(refinement,nr,17,lower,last,41);assert(i==0);
        assert(refinement[i].conditioned_cfo==cfo&&refinement[i].verification[2]==.7);
        assert(refinement_cache_find(refinement,nr,18,lower,last,41)<0);
        assert(refinement_cache_find(refinement,nr,17,nextafter(lower,INFINITY),last,41)<0);
        assert(refinement_cache_find(refinement,nr,17,lower,nextafter(last,-INFINITY),41)<0);
        assert(refinement_cache_find(refinement,nr,17,lower,last,40)<0);
        refinement_cache_entry zeros[1]={{.epoch=17,.nf=41,.lower=0,.last=last}};
        assert(refinement_cache_find(zeros,1,17,-0.0,last,41)<0);
        /* Clipped lower grids can share start/count but append distinct stops
         * within one 100-Hz bucket. Their tails must prevent reuse. */
        double a[64],b[64];int na=grid(-400000,-396012.25,100,a),nb=grid(-400000,-396087.75,100,b);
        assert(na==nb&&a[0]==b[0]&&a[na-1]!=b[nb-1]);
        refinement_cache_entry clipped[1]={{.epoch=9,.nf=na,.lower=a[0],.last=a[na-1]}};
        assert(refinement_cache_find(clipped,1,9,b[0],b[nb-1],nb)<0);
        assert(glrt_cache_find(final,ng,17,cfo)<0);
        final[ng++]=(glrt_cache_entry){17,cfo,{.1,.2,.3}};
        i=glrt_cache_find(final,ng,17,cfo);assert(i==0&&final[i].score[1]==.2);
        assert(glrt_cache_find(final,ng,18,cfo)<0);
        assert(glrt_cache_find(final,ng,17,nextafter(cfo,INFINITY))<0);
        glrt_cache_entry gzero[1]={{.epoch=17,.cfo=0,.score={0}}};assert(glrt_cache_find(gzero,1,17,-0.0)<0);
    }
}

static void zero_run(uint32_t rate,size_t count)
{
    size_t n=(rate+375)/750;
    leo_presence_complex *reference=calloc(n,sizeof(*reference)),*samples=calloc(count,sizeof(*samples));
    assert(reference&&samples);
    for(size_t k=0;k<n;++k){reference[k].re=(float)cos(.01*k);reference[k].im=(float)sin(.01*k);}
    leo_presence_workspace *w=leo_presence_create(rate,reference,reference,n);assert(w);
    leo_full_search_result result;assert(!leo_full_search_run(w,samples,count,&result));
    assert(result.candidate_count==0&&result.refinement_cache_hits==0&&result.glrt_cache_hits==0);
    assert(leo_full_search_run(w,samples,count,NULL)==-1);
    leo_presence_destroy(w);free(samples);free(reference);
}

int main(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;++r){key_tests(rates[r]);zero_run(rates[r],(size_t)ceil(rates[r]/375.0));zero_run(rates[r],rates[r]/50);}
    puts("refinement cache passed: cold/hit/near-unequal/signed-zero/reset/all-rate partial+full zero");return 0;
}
