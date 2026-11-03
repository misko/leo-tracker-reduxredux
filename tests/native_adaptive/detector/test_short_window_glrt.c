#define _GNU_SOURCE
#include "short_window_glrt.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

static int load(const char *path,void *data,size_t bytes)
{
    FILE *file=fopen(path,"rb");
    if(!file)return -1;
    int failed=fread(data,1,bytes,file)!=bytes;
    fclose(file);return failed;
}

int main(int argc,char **argv)
{
    if(argc!=4)return 2;
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    for(size_t i=0;i<4;++i){
        size_t times=0,rows=0;
        if(leo_native_glrt_short_window_layout(rates[i],&times,&rows)||
           times!=rates[i]/50||rows!=2)return 3;
        if(leo_single_rx_glrt_short_window_layout(rates[i],&times,&rows)||
           times!=rates[i]/50||rows!=1)return 3;
        if(leo_native_glrt_layout(rates[i],20,20,&times,&rows)!=
           LEO_NATIVE_GLRT_INVALID||
           leo_single_rx_glrt_layout(rates[i],20,20,&times,&rows)!=
           LEO_NATIVE_GLRT_INVALID)return 3;
    }
    size_t times=99,rows=99;
    if(leo_native_glrt_short_window_layout(1,&times,&rows)!=LEO_NATIVE_GLRT_INVALID||
       times!=99||rows!=99||
       leo_native_glrt_short_window_layout(2500000,NULL,&rows)!=LEO_NATIVE_GLRT_INVALID)
        return 4;
    const size_t count=(2500000u+375u)/750u,window=50000,bytes=window*8;
    leo_native_glrt_complex *exact=malloc(count*sizeof(*exact));
    leo_native_glrt_complex *control=malloc(count*sizeof(*control));
    long page=sysconf(_SC_PAGESIZE);
    size_t support_pages=(bytes+(size_t)page-1)/(size_t)page;
    size_t map_bytes=(support_pages+1)*(size_t)page;
    unsigned char *mapping=mmap(NULL,map_bytes,PROT_READ|PROT_WRITE,
        MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    if(!exact||!control||mapping==MAP_FAILED)return 5;
    unsigned char *boundary=mapping+support_pages*(size_t)page;
    if(mprotect(boundary,(size_t)page,PROT_NONE))return 5;
    int16_t *input=(int16_t *)(boundary-bytes);
    if(load(argv[1],exact,count*sizeof(*exact))||
       load(argv[2],control,count*sizeof(*control))||load(argv[3],input,bytes))return 6;
    leo_native_glrt *context=NULL;
    if(leo_native_glrt_create(&context,2500000,exact,control,count))return 7;
    leo_native_glrt_result result,sentinel;
    leo_native_glrt_profile profile,profile_sentinel;
    memset(&sentinel,0x5a,sizeof(sentinel));result=sentinel;
    memset(&profile_sentinel,0x5a,sizeof(profile_sentinel));profile=profile_sentinel;
    const size_t invalid_counts[]={0,window-1,window+1,window*6};
    for(size_t i=0;i<4;++i)
        if(leo_native_glrt_analyze_short_window_profiled(context,input,
           invalid_counts[i],&result,&profile)!=LEO_NATIVE_GLRT_INVALID||
           memcmp(&result,&sentinel,sizeof(result))||
           memcmp(&profile,&profile_sentinel,sizeof(profile)))return 8;
    if(leo_native_glrt_analyze_short_window(context,NULL,window,&result)!=
       LEO_NATIVE_GLRT_INVALID||
       leo_native_glrt_analyze_short_window(NULL,input,window,&result)!=
       LEO_NATIVE_GLRT_INVALID||
       leo_native_glrt_analyze(context,input,window,20,20,&result)!=
       LEO_NATIVE_GLRT_INVALID)return 8;
    if(leo_native_glrt_analyze_short_window_profiled(context,input,window,&result,&profile)||
       result.row_count!=2||profile.prepared_complex_times!=window)return 9;
    for(size_t i=0;i<2;++i)
        if(result.rows[i].receiver_id!=(int)i||result.rows[i].probe_index||
           result.rows[i].probe_start_ms)return 9;
    if(leo_native_glrt_destroy(context))return 10;
    leo_single_rx_glrt *single=NULL;
    if(leo_single_rx_glrt_create(&single,2500000,exact,control,count))return 11;
    /* Place single RX support immediately before the inaccessible page too. */
    int16_t *single_input=malloc(window*2*sizeof(*single_input));
    if(!single_input)return 12;
    for(size_t i=0;i<window;++i){single_input[2*i]=input[4*i];single_input[2*i+1]=input[4*i+1];}
    int16_t *single_boundary=(int16_t *)(boundary-window*4);
    memcpy(single_boundary,single_input,window*4);free(single_input);
    leo_native_glrt_result single_result;
    if(leo_single_rx_glrt_analyze_short_window_profiled(single,single_boundary,window,
       &single_result,&profile)||single_result.row_count!=1||
       profile.prepared_complex_times!=window)return 13;
    const leo_native_glrt_row *a=&result.rows[0],*b=&single_result.rows[0];
    if(a->candidate_count!=b->candidate_count||!a->candidate_count)return 14;
    for(int i=0;i<a->candidate_count;++i)
        if(a->candidates[i].epoch!=b->candidates[i].epoch||
           a->candidates[i].exact_score!=b->candidates[i].exact_score||
           a->candidates[i].control_score!=b->candidates[i].control_score||
           a->candidates[i].tracking_cfo_hz!=b->candidates[i].tracking_cfo_hz)return 14;
    if(leo_single_rx_glrt_destroy(single))return 15;
    munmap(mapping,map_bytes);free(control);free(exact);return 0;
}
