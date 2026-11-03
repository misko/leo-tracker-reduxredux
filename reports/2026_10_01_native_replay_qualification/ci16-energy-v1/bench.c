#define _POSIX_C_SOURCE 200809L
#include DWELL_INPUT_HEADER
#include <stdio.h>
#include <time.h>

static double cpu(void) {
    struct timespec ts;
    if(clock_gettime(CLOCK_PROCESS_CPUTIME_ID,&ts))abort();
    return ts.tv_sec+ts.tv_nsec*1e-9;
}
int main(void) {
    const size_t n=50000;const unsigned repeats=256;
    int16_t *iq=malloc(4*n*sizeof(*iq));if(!iq)return 2;
    uint32_t state=918273;
    for(size_t i=0;i<4*n;++i) {
        state=state*1664525u+1013904223u;
        iq[i]=(int16_t)((int)(state>>16)-32768);
    }
    leo_dwell_input d={0};if(leo_dwell_input_prepare(&d,iq,n))return 3;
    double start=cpu();
    for(unsigned i=0;i<repeats;++i)
        if(leo_dwell_input_prepare_reuse(&d,iq,n))return 3;
    double elapsed=cpu()-start;
    printf("{\"cpu_s\":%.17g,\"repeats\":%u,\"checksum\":%.17g}\n",
        elapsed,repeats,d.prefix[0][n]+d.prefix[1][n]);
    leo_dwell_input_free(&d);free(iq);return 0;
}
