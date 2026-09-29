/* A permutation leaves each digit histogram unchanged. Compute all three
 * once, then use stable LSD scatters. Scores and tie ordering are unchanged. */
static ranked *rank_radix(ranked *data,ranked *scratch,size_t n){
    uint32_t positions[5120]={0};
    uint32_t *p0=positions,*p1=positions+2048,*p2=positions+4096;
    for(size_t i=0;i<n;i++){
        uint32_t key=score_key(data[i].score);
        ++p0[key&2047];++p1[(key>>11)&2047];++p2[key>>22];
    }
    uint32_t sum0=0,sum1=0,sum2=0;
    for(unsigned k=0;k<2048;k++){
        uint32_t c0=p0[k],c1=p1[k];p0[k]=sum0;p1[k]=sum1;
        sum0+=c0;sum1+=c1;
    }
    for(unsigned k=0;k<1024;k++){
        uint32_t count=p2[k];p2[k]=sum2;sum2+=count;
    }
    for(size_t i=0;i<n;i++)scratch[p0[score_key(data[i].score)&2047]++]=data[i];
    for(size_t i=0;i<n;i++)data[p1[(score_key(scratch[i].score)>>11)&2047]++]=scratch[i];
    for(size_t i=0;i<n;i++)scratch[p2[score_key(data[i].score)>>22]++]=data[i];
    return scratch;
}
