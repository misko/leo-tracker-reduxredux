#define LEO_PROPOSAL_LIBRARY 1
#define LEO_PROPOSAL_OMIT_POWER 1
#include "proposal_core.c"
#include <assert.h>

static int original_flat(const float *s,size_t n){
    float lo=s[0],hi=lo;for(size_t k=1;k<n;k++){if(s[k]<lo)lo=s[k];if(s[k]>hi)hi=s[k];}
    return hi-lo<=16*FLT_EPSILON*fmaxf(fmaxf(fabsf(lo),fabsf(hi)),1.0f);
}
int main(void){
    const float re[]={0,3,-4,1e20f,FLT_MAX},im[]={0,4,3,-1e20f,FLT_MAX},scale[]={1,0.25f,0.25f,1e-20f,1.0f/FLT_MAX};
    float mag[5],squared[5];for(int k=0;k<5;k++){float sr=re[k]*scale[k],si=im[k]*scale[k];mag[k]=hypotf(sr,si);squared[k]=rank_squared_magnitude(re[k],im[k],scale[k]);assert(isfinite(squared[k]));}
    for(int a=0;a<5;a++)for(int b=0;b<5;b++)assert((mag[a]<mag[b])==(squared[a]<squared[b]));
    float flat_mag[4]={1,1+4*FLT_EPSILON,1+8*FLT_EPSILON,1+12*FLT_EPSILON},flat_sq[4];
    for(int k=0;k<4;k++)flat_sq[k]=flat_mag[k]*flat_mag[k];assert(original_flat(flat_mag,4)==rank_feature_flat(flat_sq,4));
    const unsigned rates[]={2500000,5000000,7500000,10000000};
    for(int r=0;r<4;r++){size_t n=(rates[r]+375)/750,dwell=(size_t)rates[r]*120/1000;double (*t)[2]=calloc(n,sizeof(*t));int16_t *raw=calloc(4*dwell,sizeof(*raw));assert(t&&raw);
        for(size_t k=0;k<n;k++){t[k][0]=cos(0.01*k);t[k][1]=sin(0.01*k);}leo_proposal_workspace *w=leo_proposal_create(t,n,rates[r]);assert(w);int centers[4],count;leo_proposal_timing timing;
        assert(!leo_proposal_top4(w,raw,0,0,centers,&count,&timing));assert(count==0);for(size_t k=0;k<4*dwell;k++)raw[k]=(k&1)?INT16_MIN:INT16_MAX;
        assert(!leo_proposal_top4(w,raw,0,1,centers,&count,&timing));assert(count>=0&&count<=4);assert(isfinite(timing.total_ms));leo_proposal_destroy(w);free(raw);free(t);}
    puts("rank-only squared magnitude: ordering flat-gate zero/extreme all-rates ok");return 0;
}
