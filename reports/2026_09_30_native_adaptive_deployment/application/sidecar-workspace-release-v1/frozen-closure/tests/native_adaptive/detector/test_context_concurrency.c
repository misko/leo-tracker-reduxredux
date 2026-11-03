#define _POSIX_C_SOURCE 200809L

#include "native_glrt.h"

#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    leo_native_glrt *context;
    const int16_t *samples;
    size_t complex_times;
    pthread_barrier_t *barrier;
    leo_native_glrt_result result;
    int status;
} call;

static void *read_file(const char *path,size_t size,size_t *count)
{
    FILE *stream=fopen(path,"rb");
    if(!stream||fseek(stream,0,SEEK_END))return NULL;
    long length=ftell(stream);
    if(length<0||(size_t)length%size||fseek(stream,0,SEEK_SET))return NULL;
    void *data=malloc((size_t)length);
    if(!data||fread(data,1,(size_t)length,stream)!=(size_t)length){
        free(data);fclose(stream);return NULL;
    }
    fclose(stream);*count=(size_t)length/size;return data;
}

static void scrub_timings(leo_native_glrt_result *result)
{
    result->detector_cpu_ms=0;
    for(size_t i=0;i<result->row_count;++i){
        leo_native_glrt_row *row=&result->rows[i];
        row->total_cpu_ms=0;row->proposal_ms=0;row->stage_sum_ms=0;
        row->proposal_fold_ms=0;row->proposal_correlation_ms=0;
        row->proposal_ranking_ms=0;row->coarse_ms=0;row->acquisition_ms=0;
        row->fine_fft_ms=0;row->conditioned_ms=0;row->verification_ms=0;
        row->glrt_ms=0;row->fractional_epoch_ms=0;
    }
}

static void *run_call(void *opaque)
{
    call *item=opaque;
    pthread_barrier_wait(item->barrier);
    item->status=leo_native_glrt_analyze(item->context,item->samples,
        item->complex_times,120,120,&item->result);
    return NULL;
}

static int concurrent_pair(call *left,call *right)
{
    pthread_barrier_t barrier;
    pthread_t threads[2];
    if(pthread_barrier_init(&barrier,NULL,2))return -1;
    left->barrier=&barrier;right->barrier=&barrier;
    if(pthread_create(&threads[0],NULL,run_call,left)||
       pthread_create(&threads[1],NULL,run_call,right))return -1;
    pthread_join(threads[0],NULL);pthread_join(threads[1],NULL);
    pthread_barrier_destroy(&barrier);return 0;
}

static int same_context_busy(leo_native_glrt *context,const int16_t *samples,
    size_t complex_times)
{
    for(int attempt=0;attempt<4;++attempt){
        call left={.context=context,.samples=samples,.complex_times=complex_times};
        call right=left;
        if(concurrent_pair(&left,&right))return -1;
        if((left.status==LEO_NATIVE_GLRT_OK&&right.status==LEO_NATIVE_GLRT_BUSY)||
           (right.status==LEO_NATIVE_GLRT_OK&&left.status==LEO_NATIVE_GLRT_BUSY))
            return 0;
        if(left.status!=LEO_NATIVE_GLRT_OK||right.status!=LEO_NATIVE_GLRT_OK)return -1;
    }
    return -1;
}

static int compare_without_timings(leo_native_glrt_result left,
    leo_native_glrt_result right)
{
    scrub_timings(&left);scrub_timings(&right);
    return !memcmp(&left,&right,sizeof(left));
}

static int candidate_count(const leo_native_glrt_result *result)
{
    int count=0;
    for(size_t row=0;row<result->row_count;++row)
        count+=result->rows[row].candidate_count;
    return count;
}

static int real_fixture(const char *exact_path,const char *control_path,
    const char *raw_path,const char *other_raw_path)
{
    size_t exact_count=0,control_count=0,scalar_count=0,other_scalar_count=0;
    leo_native_glrt_complex *exact=read_file(exact_path,sizeof(*exact),&exact_count);
    leo_native_glrt_complex *control=read_file(control_path,sizeof(*control),&control_count);
    int16_t *samples=read_file(raw_path,sizeof(*samples),&scalar_count);
    int16_t *other_samples=read_file(other_raw_path,sizeof(*other_samples),&other_scalar_count);
    if(!exact||!control||!samples||!other_samples||exact_count!=control_count||
       scalar_count!=1200000||other_scalar_count!=scalar_count)
        return -1;
    leo_native_glrt *ordinary=NULL,*fractional=NULL;
    if(leo_native_glrt_create_with_mode(&ordinary,2500000,exact,control,exact_count,
        LEO_NATIVE_GLRT_MODE_ORDINARY)||
       leo_native_glrt_create_with_mode(&fractional,2500000,exact,control,exact_count,
        LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH))return -1;
    leo_native_glrt_result ordinary_expected,fractional_expected;
    if(leo_native_glrt_analyze(ordinary,samples,300000,120,120,&ordinary_expected)||
       leo_native_glrt_analyze(fractional,other_samples,300000,120,120,&fractional_expected)||
       !candidate_count(&ordinary_expected)||!candidate_count(&fractional_expected)||
       compare_without_timings(ordinary_expected,fractional_expected))return -1;
    call left={.context=ordinary,.samples=samples,.complex_times=300000};
    call right={.context=fractional,.samples=other_samples,.complex_times=300000};
    if(concurrent_pair(&left,&right)||left.status||right.status||
       !compare_without_timings(left.result,ordinary_expected)||
       !compare_without_timings(right.result,fractional_expected)||
       same_context_busy(ordinary,samples,300000))return -1;
    if(leo_native_glrt_destroy(ordinary)||leo_native_glrt_destroy(fractional))return -1;
    free(other_samples);free(samples);free(control);free(exact);return 0;
}

static int synthetic_rate(uint32_t rate,leo_native_glrt **out,int16_t **samples,
    leo_native_glrt_result *expected)
{
    size_t template_count=(rate+375u)/750u,complex_times=(size_t)rate*120u/1000u;
    leo_native_glrt_complex *exact=calloc(template_count,sizeof(*exact));
    leo_native_glrt_complex *control=calloc(template_count,sizeof(*control));
    *samples=calloc(4*complex_times,sizeof(**samples));
    if(!exact||!control||!*samples)return -1;
    for(size_t i=0;i<template_count;++i){
        exact[i].real=(i&1)?-1.0:1.0;control[i].imaginary=(i&1)?1.0:-1.0;
    }
    int status=leo_native_glrt_create(out,rate,exact,control,template_count);
    free(control);free(exact);
    return status||leo_native_glrt_analyze(*out,*samples,complex_times,120,120,expected);
}

static int mixed_rates(void)
{
    leo_native_glrt *low=NULL,*high=NULL;
    int16_t *low_samples=NULL,*high_samples=NULL;
    leo_native_glrt_result low_expected,high_expected;
    if(synthetic_rate(2500000,&low,&low_samples,&low_expected)||
       synthetic_rate(7500000,&high,&high_samples,&high_expected))return -1;
    call left={.context=low,.samples=low_samples,.complex_times=300000};
    call right={.context=high,.samples=high_samples,.complex_times=900000};
    if(concurrent_pair(&left,&right)||left.status||right.status||
       !compare_without_timings(left.result,low_expected)||
       !compare_without_timings(right.result,high_expected))return -1;
    if(leo_native_glrt_destroy(low)||leo_native_glrt_destroy(high))return -1;
    free(high_samples);free(low_samples);return 0;
}

int main(int argc,char **argv)
{
    leo_native_glrt_capabilities capabilities;
    if(argc!=5||leo_native_glrt_get_capabilities(&capabilities)||
       capabilities.process_serialized||real_fixture(argv[1],argv[2],argv[3],argv[4])||
       mixed_rates())return 1;
    return 0;
}
