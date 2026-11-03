#define _POSIX_C_SOURCE 200809L

#include "native_glrt_research.h"

#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int read_file(const char *path, void **data, size_t *size)
{
    FILE *file=fopen(path,"rb");
    if(!file||fseek(file,0,SEEK_END))return -1;
    long end=ftell(file);
    if(end<=0||fseek(file,0,SEEK_SET)){fclose(file);return -1;}
    void *value=malloc((size_t)end);
    if(!value||fread(value,1,(size_t)end,file)!=(size_t)end||fgetc(file)!=EOF){
        free(value);fclose(file);return -1;
    }
    fclose(file);*data=value;*size=(size_t)end;return 0;
}

static void clear_timings(leo_native_glrt_row *row)
{
    row->total_cpu_ms=0;row->proposal_ms=0;row->stage_sum_ms=0;
    row->proposal_fold_ms=0;row->proposal_correlation_ms=0;
    row->proposal_ranking_ms=0;row->coarse_ms=0;row->acquisition_ms=0;
    row->fine_fft_ms=0;row->conditioned_ms=0;row->verification_ms=0;
    row->glrt_ms=0;row->fractional_epoch_ms=0;
}

static int science_equal(const leo_native_glrt_result *left,
    const leo_native_glrt_result *right)
{
    if(left->row_count!=right->row_count)return 0;
    for(size_t index=0;index<left->row_count;++index){
        leo_native_glrt_row a=left->rows[index],b=right->rows[index];
        clear_timings(&a);clear_timings(&b);
        if(memcmp(&a,&b,sizeof(a)))return 0;
    }
    return 1;
}

int main(int argc,char **argv)
{
    if(argc!=4)return 2;
    void *exact_data=NULL,*control_data=NULL,*raw_data=NULL;
    size_t exact_size=0,control_size=0,raw_size=0,complex_times=0,row_count=0;
    if(read_file(argv[1],&exact_data,&exact_size)||
       read_file(argv[2],&control_data,&control_size)||
       read_file(argv[3],&raw_data,&raw_size)||
       exact_size!=control_size||exact_size%sizeof(leo_native_glrt_complex)||
       leo_native_glrt_layout(2500000u,120u,120u,&complex_times,&row_count)||
       row_count!=2||raw_size!=4*complex_times*sizeof(int16_t))return 3;

    leo_native_glrt *context=NULL;
    int status=leo_native_glrt_create_with_mode(&context,2500000u,exact_data,
        control_data,exact_size/sizeof(leo_native_glrt_complex),
        LEO_NATIVE_GLRT_MODE_DEPLOYED_SERVER_INTERVAL_FRACTIONAL);
    if(status!=LEO_NATIVE_GLRT_OK)return 4;

    const double original_centers[2]={2.0,2.0};
    const double rejected_centers[2]={1002.0,2002.0};
    const double invalid_centers[2]={INFINITY,2.0};
    if(leo_native_glrt_set_server_reference_geometry(context,original_centers,
           -440000.0,440000.0)!=LEO_NATIVE_GLRT_OK||
       leo_native_glrt_set_server_reference_geometry(context,original_centers,
           -429685.5,429685.5)!=LEO_NATIVE_GLRT_OK)return 5;

    leo_native_glrt_result before={0},after={0};
    if(leo_native_glrt_analyze(context,raw_data,complex_times,120u,120u,&before)!=
       LEO_NATIVE_GLRT_OK)return 6;

    if(leo_native_glrt_set_server_reference_geometry(context,rejected_centers,
           0.0,nextafter(880000.0,INFINITY))!=LEO_NATIVE_GLRT_INVALID||
       leo_native_glrt_set_server_reference_geometry(context,rejected_centers,
           -450000.0,450000.0)!=LEO_NATIVE_GLRT_INVALID||
       leo_native_glrt_set_server_reference_geometry(context,rejected_centers,
           -440000.0,NAN)!=LEO_NATIVE_GLRT_INVALID||
       leo_native_glrt_set_server_reference_geometry(context,invalid_centers,
           -440000.0,440000.0)!=LEO_NATIVE_GLRT_INVALID)return 7;

    if(leo_native_glrt_analyze(context,raw_data,complex_times,120u,120u,&after)!=
       LEO_NATIVE_GLRT_OK||!science_equal(&before,&after))return 8;
    if(leo_native_glrt_destroy(context)!=LEO_NATIVE_GLRT_OK)return 9;
    free(raw_data);free(control_data);free(exact_data);
    puts("reference geometry: 880 kHz boundary and transactional rejection pass");
    return 0;
}
