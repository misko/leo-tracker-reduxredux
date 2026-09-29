#include "native_glrt.h"

#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static leo_native_glrt_complex *make_template(size_t count,double phase)
{
    leo_native_glrt_complex *result=malloc(count*sizeof(*result));
    assert(result);
    for(size_t i=0;i<count;++i){
        double angle=phase+.013*(double)i+.0000007*(double)(i*i);
        result[i]=(leo_native_glrt_complex){cos(angle),sin(angle)};
    }
    return result;
}

static void configuration_validation(void)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    const uint32_t dwells[]={120,240,360},strides[]={10,20,120};
    for(size_t i=0;i<sizeof(rates)/sizeof(rates[0]);++i){
        for(size_t d=0;d<3;++d)for(size_t s=0;s<3;++s){
            size_t times=0,rows=0;
            assert(!leo_native_glrt_layout(rates[i],dwells[d],strides[s],&times,&rows));
            assert(times==(size_t)rates[i]*dwells[d]/1000u);
            assert(rows==2u*(1u+(dwells[d]-20u)/strides[s]));
        }
        size_t count=(rates[i]+375u)/750u;
        leo_native_glrt_complex *exact=make_template(count,.2);
        leo_native_glrt_complex *control=make_template(count,1.1);
        leo_native_glrt *context=NULL;
        assert(leo_native_glrt_create(&context,rates[i],exact,control,count)==0);
        leo_native_glrt_result output={0};
        int16_t dummy[4]={0};
        assert(leo_native_glrt_analyze(context,dummy,1,120,10,&output)==LEO_NATIVE_GLRT_INVALID);
        assert(leo_native_glrt_analyze(context,dummy,1,180,10,&output)==LEO_NATIVE_GLRT_INVALID);
        assert(leo_native_glrt_analyze(context,dummy,1,120,30,&output)==LEO_NATIVE_GLRT_INVALID);
        assert(leo_native_glrt_destroy(context)==0);
        free(control);free(exact);
    }
    leo_native_glrt *invalid=NULL;
    leo_native_glrt_complex value={0};
    assert(leo_native_glrt_create(&invalid,3000000,&value,&value,1)==LEO_NATIVE_GLRT_INVALID);
    size_t count=(2500000u+375u)/750u;
    leo_native_glrt_complex *bad=make_template(count,.2);
    leo_native_glrt_complex *good=make_template(count,1.1);
    bad[count/2].real=NAN;
    assert(leo_native_glrt_create(&invalid,2500000,bad,good,count)==LEO_NATIVE_GLRT_INVALID);
    bad[count/2].real=17;
    assert(leo_native_glrt_create(&invalid,2500000,bad,good,count)==LEO_NATIVE_GLRT_INVALID);
    free(good);free(bad);
}

static void assert_same_science(const leo_native_glrt_row *a,
    const leo_native_glrt_row *b)
{
    assert(a->receiver_id==b->receiver_id);
    assert(a->probe_start_ms==b->probe_start_ms);
    assert(a->candidate_count==b->candidate_count);
    assert(a->retained_peak_count==b->retained_peak_count);
    assert(a->coarse_gate_skipped_count==b->coarse_gate_skipped_count);
    assert(a->conditioned_fallback_count==b->conditioned_fallback_count);
    assert(a->actual_executed_glrt_calls==b->actual_executed_glrt_calls);
    assert(a->glrt_cache_hits==b->glrt_cache_hits);
    assert(a->conditioned_cache_hits==b->conditioned_cache_hits);
    assert(a->fine_fft_cache_entries==b->fine_fft_cache_entries);
    assert(a->fine_fft_cache_hits==b->fine_fft_cache_hits);
    for(int i=0;i<a->candidate_count;++i)
        assert(!memcmp(&a->candidates[i],&b->candidates[i],sizeof(a->candidates[i])));
}

static void shared_anchor_numerics(void)
{
    const uint32_t rate=2500000,dwell_ms=120;
    size_t frame=(rate+375u)/750u,times=(size_t)rate*dwell_ms/1000u;
    leo_native_glrt_complex *exact=make_template(frame,.2);
    leo_native_glrt_complex *control=make_template(frame,1.1);
    int16_t *input=calloc(4*times,sizeof(*input));assert(input);
    double *accumulated=calloc(2*times,sizeof(*accumulated));assert(accumulated);
    for(int frame_index=0;frame_index<16;++frame_index){
        size_t offset=(size_t)llround((double)frame_index*rate/750.0);
        for(size_t k=0;k<frame&&offset+k<rate/50u;++k){
            accumulated[2*(offset+k)]+=12000*exact[k].real;
            accumulated[2*(offset+k)+1]+=12000*exact[k].imaginary;
        }
    }
    for(size_t k=0;k<times;++k)for(int rx=0;rx<2;++rx){
        long real=lround(accumulated[2*k]),imaginary=lround(accumulated[2*k+1]);
        if(real>32767)real=32767;
        if(real<-32768)real=-32768;
        if(imaginary>32767)imaginary=32767;
        if(imaginary<-32768)imaginary=-32768;
        input[4*k+2*(size_t)rx]=(int16_t)real;
        input[4*k+2*(size_t)rx+1]=(int16_t)imaginary;
    }
    leo_native_glrt *context=NULL;
    assert(!leo_native_glrt_create(&context,rate,exact,control,frame));
    leo_native_glrt_result dense,twenty,one_twenty;
    assert(!leo_native_glrt_analyze(context,input,times,dwell_ms,10,&dense));
    assert(!leo_native_glrt_analyze(context,input,times,dwell_ms,20,&twenty));
    assert(!leo_native_glrt_analyze(context,input,times,dwell_ms,120,&one_twenty));
    assert(dense.row_count==22&&twenty.row_count==12&&one_twenty.row_count==2);
    int candidates=0;
    for(size_t i=0;i<dense.row_count;++i)candidates+=dense.rows[i].candidate_count;
    assert(candidates>0);
    for(size_t window=0;window<6;++window)for(int rx=0;rx<2;++rx)
        assert_same_science(&dense.rows[4*window+(size_t)rx],
            &twenty.rows[2*window+(size_t)rx]);
    for(int rx=0;rx<2;++rx)
        assert_same_science(&dense.rows[rx],&one_twenty.rows[rx]);
    leo_native_glrt_result unchanged=dense,repeated;
    assert(leo_native_glrt_analyze(context,input,times-1,dwell_ms,10,&unchanged)==LEO_NATIVE_GLRT_INVALID);
    assert(!memcmp(&unchanged,&dense,sizeof(dense)));
    assert(!leo_native_glrt_analyze(context,input,times,dwell_ms,10,&repeated));
    assert(repeated.row_count==dense.row_count);
    for(size_t i=0;i<dense.row_count;++i)assert_same_science(&dense.rows[i],&repeated.rows[i]);
    assert(!leo_native_glrt_destroy(context));
    free(accumulated);free(input);free(control);free(exact);
}

static int supported_geometry_actual_runs(uint32_t selected_rate,
    uint32_t selected_dwell)
{
    const uint32_t rates[]={2500000,5000000,7500000,10000000};
    const uint32_t dwells[]={120,240,360};
    for(size_t r=0;r<4;++r){
        if(selected_rate&&rates[r]!=selected_rate)continue;
        size_t frame=(rates[r]+375u)/750u;
        leo_native_glrt_complex *exact=make_template(frame,.2);
        leo_native_glrt_complex *control=make_template(frame,1.1);
        leo_native_glrt *context=NULL;
        assert(!leo_native_glrt_create(&context,rates[r],exact,control,frame));
        for(size_t d=0;d<3;++d){
            if(selected_dwell&&dwells[d]!=selected_dwell)continue;
            printf("geometry rate_hz=%u dwell_ms=%u\n",rates[r],dwells[d]);
            fflush(stdout);
            size_t times=(size_t)rates[r]*dwells[d]/1000u;
            int16_t *zero=calloc(4*times,sizeof(*zero));
            if(!zero){
                fprintf(stderr,"allocation failed: rate_hz=%u dwell_ms=%u input_bytes=%zu\n",
                    rates[r],dwells[d],4*times*sizeof(*zero));
                leo_native_glrt_destroy(context);free(control);free(exact);
                return 1;
            }
            leo_native_glrt_result dense,twenty,one_twenty;
            uint32_t failed_stride=10;
            int status=leo_native_glrt_analyze(context,zero,times,dwells[d],10,&dense);
            if(!status){
                failed_stride=20;
                status=leo_native_glrt_analyze(context,zero,times,dwells[d],20,&twenty);
            }
            if(!status){
                failed_stride=120;
                status=leo_native_glrt_analyze(context,zero,times,dwells[d],120,&one_twenty);
            }
            if(status){
                fprintf(stderr,
                    "analysis failed: rate_hz=%u dwell_ms=%u stride_ms=%u status=%d\n",
                    rates[r],dwells[d],failed_stride,status);
                free(zero);leo_native_glrt_destroy(context);free(control);free(exact);
                return 1;
            }
            assert(dense.row_count==2u*(1u+(dwells[d]-20u)/10u));
            assert(twenty.row_count==2u*(1u+(dwells[d]-20u)/20u));
            assert(one_twenty.row_count==2u*(1u+(dwells[d]-20u)/120u));
            for(size_t window=0;window<twenty.row_count/2;++window)
                for(int rx=0;rx<2;++rx)
                    assert_same_science(&dense.rows[4*window+(size_t)rx],
                        &twenty.rows[2*window+(size_t)rx]);
            for(size_t window=0;window<one_twenty.row_count/2;++window)
                for(int rx=0;rx<2;++rx)
                    assert_same_science(&dense.rows[24*window+(size_t)rx],
                        &one_twenty.rows[2*window+(size_t)rx]);
            free(zero);
        }
        assert(!leo_native_glrt_destroy(context));free(control);free(exact);
    }
    return 0;
}

static int parse_selection(int argc,char **argv,uint32_t *rate,uint32_t *dwell)
{
    if(argc==1){*rate=0;*dwell=0;return 0;}
    if(argc!=5)return -1;
    int seen_rate=0,seen_dwell=0;
    for(int i=1;i<argc;i+=2){
        char *end=NULL;
        unsigned long value=strtoul(argv[i+1],&end,10);
        if(!argv[i+1][0]||*end||value>UINT32_MAX)return -1;
        if(!strcmp(argv[i],"--rate-hz")&&!seen_rate){
            *rate=(uint32_t)value;seen_rate=1;
        }else if(!strcmp(argv[i],"--dwell-ms")&&!seen_dwell){
            *dwell=(uint32_t)value;seen_dwell=1;
        }else return -1;
    }
    if((*rate!=2500000&&*rate!=5000000&&*rate!=7500000&&*rate!=10000000)||
       (*dwell!=120&&*dwell!=240&&*dwell!=360))return -1;
    return 0;
}

int main(int argc,char **argv)
{
    uint32_t rate=0,dwell=0;
    if(parse_selection(argc,argv,&rate,&dwell)){
        fprintf(stderr,"usage: %s [--rate-hz RATE --dwell-ms 120|240|360]\n",argv[0]);
        return 2;
    }
    configuration_validation();
    shared_anchor_numerics();
    if(supported_geometry_actual_runs(rate,dwell))return 1;
    puts("native GLRT RAM API tests passed");
    return 0;
}
