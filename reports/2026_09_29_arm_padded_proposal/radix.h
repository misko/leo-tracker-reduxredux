/* Stable float sorting. Input indices are ascending; ties retain that order.
 * Finite scores only. Both signed zeros share a key, matching the comparator. */
static uint32_t score_key(float value) {
    uint32_t bits; if(value==0) value=0;
    memcpy(&bits,&value,sizeof(bits));
    return bits&0x80000000u ? ~bits : bits^0x80000000u;
}
static void rank_radix(ranked *data, ranked *scratch, size_t n) {
    ranked *src=data,*dst=scratch;
    for(unsigned shift=0;shift<32;shift+=8) {
        size_t counts[256]={0},positions[256],sum=0;
        for(size_t i=0;i<n;i++)++counts[(score_key(src[i].score)>>shift)&255];
        for(unsigned k=0;k<256;k++){positions[k]=sum;sum+=counts[k];}
        for(size_t i=0;i<n;i++)dst[positions[(score_key(src[i].score)>>shift)&255]++]=src[i];
        ranked *tmp=src;src=dst;dst=tmp;
    }
}
