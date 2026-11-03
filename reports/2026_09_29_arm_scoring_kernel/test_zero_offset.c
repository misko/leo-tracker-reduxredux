/* The raw diagnostic must reject unsupported offsets before touching IQ. */
#define main scorer_probe_main
#include "probe.c"
#undef main
int main(void) {
    const double offsets[]={0.5,-0.5,1,-1,NAN,INFINITY,-INFINITY};
    double result[3];
    for(size_t i=0;i<sizeof(offsets)/sizeof(offsets[0]);++i)
        if(glrt(NULL,0,0,0,offsets[i],16,1,result)!=-1) return 1;
    puts("unsupported offsets rejected before input access");
    return 0;
}
