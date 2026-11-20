/* Invert the positive sample-lag phase of the existing complex pilot scout. */
#ifndef LEO_PHASE_SCOUT_MASK_H
#define LEO_PHASE_SCOUT_MASK_H

#include <math.h>
#include <stdint.h>

#define PHASE_SCOUT_BINS 21
#define PHASE_SCOUT_ALL ((UINT32_C(1) << PHASE_SCOUT_BINS) - 1)
#define PHASE_SCOUT_STEP 80000.0
#define PHASE_SCOUT_LOW (-800000.0)

static uint32_t phase_scout_mask(const float iq[3][2], double rate,
    double hz[3], double rho[3])
{
    static const int lag[3]={1,3,5};
    const double tau=6.283185307179586476925286766559;
    for(int i=0;i<3;++i){
        rho[i]=hypot((double)iq[i][0],(double)iq[i][1]);
        hz[i]=atan2((double)iq[i][1],(double)iq[i][0])*rate/(tau*lag[i]);
    }
    if(rate!=10000000.0)return PHASE_SCOUT_ALL;
    for(int i=0;i<3;++i) {
        if(!(rho[i]>=0.04) || !isfinite(hz[i]) || fabs(hz[i])>880000.0)
            return PHASE_SCOUT_ALL;
    }
    if(fabs(hz[1]-hz[2])>PHASE_SCOUT_STEP ||
       fabs(hz[0]-hz[2])>2.0*PHASE_SCOUT_STEP)return PHASE_SCOUT_ALL;
    double sum=0,weight=0;
    for(int i=0;i<3;++i){
        double w=lag[i]*rho[i];
        w*=w;sum+=w*hz[i];weight+=w;
    }
    int center=(int)lround((sum/weight-PHASE_SCOUT_LOW)/PHASE_SCOUT_STEP);
    uint32_t mask=0;
    for(int i=center-2;i<=center+2;++i)
        if(i>=0&&i<PHASE_SCOUT_BINS)mask|=UINT32_C(1)<<i;
    return mask?mask:PHASE_SCOUT_ALL;
}

#endif
