#define _POSIX_C_SOURCE 200809L

#include "native_glrt.h"

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

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

static long rss_kib(void)
{
    FILE *stream=fopen("/proc/self/status","r");
    char line[256];long result=-1;
    if(!stream)return -1;
    while(fgets(line,sizeof(line),stream))
        if(sscanf(line,"VmRSS: %ld kB",&result)==1)break;
    fclose(stream);return result;
}

int main(int argc,char **argv)
{
    if(argc!=5)return 2;
    char *end=NULL;unsigned long mode=strtoul(argv[1],&end,10);
    if(!end||*end||mode>1)return 2;
    size_t exact_count=0,control_count=0,scalar_count=0;
    leo_native_glrt_complex *exact=read_file(argv[2],sizeof(*exact),&exact_count);
    leo_native_glrt_complex *control=read_file(argv[3],sizeof(*control),&control_count);
    int16_t *samples=read_file(argv[4],sizeof(*samples),&scalar_count);
    if(!exact||!control||!samples||exact_count!=control_count||scalar_count!=1200000)
        return 3;
    long baseline=rss_kib(),after[2]={-1,-1};
    leo_native_glrt *contexts[2]={NULL,NULL};
    leo_native_glrt_result *result=malloc(sizeof(*result));
    if(!result)return 3;
    for(int i=0;i<2;++i){
        if(leo_native_glrt_create_with_mode(&contexts[i],2500000,exact,control,
            exact_count,(uint32_t)mode)||
           leo_native_glrt_analyze(contexts[i],samples,300000,120,120,result))return 4;
        after[i]=rss_kib();
    }
    printf("{\"mode\":%lu,\"baseline_rss_kib\":%ld,"
           "\"one_warmed_context_rss_kib\":%ld,"
           "\"two_warmed_contexts_rss_kib\":%ld,"
           "\"first_increment_kib\":%ld,\"second_increment_kib\":%ld}\n",
        mode,baseline,after[0],after[1],after[0]-baseline,after[1]-after[0]);
    if(leo_native_glrt_destroy(contexts[0])||leo_native_glrt_destroy(contexts[1]))return 4;
    free(result);free(samples);free(control);free(exact);return 0;
}
