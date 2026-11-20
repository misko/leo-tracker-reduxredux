#define _POSIX_C_SOURCE 200809L
#include "short_window_glrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

static int load(const char *path, void *out, size_t size)
{
    FILE *file=fopen(path,"rb");
    if (!file) return -1;
    int ok=fread(out,1,size,file)==size && fgetc(file)==EOF;
    fclose(file);
    return ok ? 0 : -1;
}

static double wall_ms(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC,&ts)) return -1;
    return 1000.0*ts.tv_sec+1e-6*ts.tv_nsec;
}

int main(int argc, char **argv)
{
    const uint32_t rate=10000000;
    const size_t samples=rate/50, frame=(rate+375)/750;
    if (argc!=4) return 1;
    int16_t *iq=malloc(4*samples*sizeof(*iq));
    leo_native_glrt_complex *exact=malloc(frame*sizeof(*exact));
    leo_native_glrt_complex *control=malloc(frame*sizeof(*control));
    leo_native_glrt_result *result=malloc(sizeof(*result));
    if (!iq || !exact || !control || !result || load(argv[1],iq,4*samples*sizeof(*iq)) ||
        load(argv[2],exact,frame*sizeof(*exact)) || load(argv[3],control,frame*sizeof(*control)))
        return 2;
    leo_native_glrt *context=NULL;
    double start=wall_ms();
    if (leo_native_glrt_create_with_mode(&context,rate,exact,control,frame,
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH)) return 3;
    printf("%.6f\n",wall_ms()-start);
    printf("cpu_ms,wall_ms,preparation_cpu_ms,search_cpu_ms,fine_fft_cpu_ms,alloc_cleanup_cpu_ms\n");
    for (int i=0;i<5;++i) {
        leo_native_glrt_profile profile;
        start=wall_ms();
        if (leo_native_glrt_analyze_short_window_profiled(context,iq,samples,result,&profile))
            return 4;
        double wall=wall_ms()-start;
        double fine=0;
        for (size_t rx=0;rx<result->row_count;++rx) fine+=result->rows[rx].fine_fft_ms;
        printf("%.6f,%.6f,%.6f,%.6f,%.6f,%.6f\n",result->detector_cpu_ms,wall,
            profile.preparation_cpu_ms,profile.search_cpu_ms,fine,
            profile.allocation_cpu_ms+profile.cleanup_cpu_ms);
    }
    free(result);free(control);free(exact);free(iq);
    return leo_native_glrt_destroy(context) ? 5 : 0;
}
