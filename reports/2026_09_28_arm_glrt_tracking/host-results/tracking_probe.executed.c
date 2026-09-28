#define _GNU_SOURCE
#include "track.h"
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef LEO_FULL_ARM_AFFINITY
#include <sched.h>
#endif

enum { WINDOWS=11, RECEIVERS=2 };

static void *read_all(const char *path,size_t n,size_t item)
{
    FILE *f=fopen(path,"rb"); void *p=calloc(n,item);
    if(!f||!p||fread(p,item,n,f)!=n||fgetc(f)!=EOF){if(f)fclose(f);free(p);return NULL;}
    fclose(f); return p;
}

static void emit_error(int rx,int window,const char *error)
{
    printf("{\"type\":\"window\",\"status\":\"error\",\"receiver_id\":%d,"
        "\"probe_index\":%d,\"error\":\"%s\",\"candidates\":[]}\n",rx,window,error);
}

static void emit_result(int rx,int window,const char *mode,int fallback,
    const leo_tracking_result *r)
{
    printf("{\"type\":\"window\",\"status\":\"ok\",\"receiver_id\":%d,"
        "\"probe_index\":%d,\"mode\":\"%s\",\"fallback_triggered\":%s,"
        "\"candidate_count\":%d,\"positive_count\":%d,"
        "\"candidate_eval_attempts\":%d,\"timings_ms\":{\"total_cpu\":%.17g,"
        "\"conversion\":%.17g,\"coarse\":%.17g,\"acquisition\":%.17g,"
        "\"fine_fft\":%.17g,\"conditioned\":%.17g,\"verification\":%.17g,"
        "\"glrt\":%.17g},\"candidates\":[",rx,window,mode,fallback?"true":"false",
        r->candidate_count,r->positive_count,r->candidate_eval_attempts,r->total_cpu_ms,
        r->conversion_cpu_ms,r->coarse_cpu_ms,r->acquisition_cpu_ms,r->fine_fft_cpu_ms,
        r->conditioned_cpu_ms,r->verification_cpu_ms,r->glrt_cpu_ms);
    for(int i=0;i<r->candidate_count;++i){const leo_tracking_candidate *c=&r->candidates[i];
        printf("%s{\"seed_rank\":%d,\"epoch\":%d,\"epoch_delta\":%d,"
            "\"glrt_complete\":%d,\"acquisition_fields_valid\":%s,"
            "\"coarse_fields_valid\":%s,\"verification_fields_valid\":%s,"
            "\"acquired_cfo_hz\":%.17g,\"tracking_cfo_hz\":%.17g,"
            "\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g}",
            i?",":"",c->seed_rank,c->epoch,c->epoch_delta,c->glrt_complete,
            c->acquisition_fields_valid?"true":"false",c->coarse_fields_valid?"true":"false",
            c->verification_fields_valid?"true":"false",c->acquired_cfo_hz,
            c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
    }
    puts("]}"); fflush(stdout);
}

static void add_cost(leo_tracking_result *dst,const leo_tracking_result *attempt)
{
    dst->candidate_eval_attempts+=attempt->candidate_eval_attempts;
    dst->conversion_cpu_ms+=attempt->conversion_cpu_ms;
    dst->coarse_cpu_ms+=attempt->coarse_cpu_ms;
    dst->acquisition_cpu_ms+=attempt->acquisition_cpu_ms;
    dst->fine_fft_cpu_ms+=attempt->fine_fft_cpu_ms;
    dst->conditioned_cpu_ms+=attempt->conditioned_cpu_ms;
    dst->verification_cpu_ms+=attempt->verification_cpu_ms;
    dst->glrt_cpu_ms+=attempt->glrt_cpu_ms;
    dst->total_cpu_ms+=attempt->total_cpu_ms;
}

int main(int argc,char **argv)
{
#ifdef LEO_FULL_ARM_AFFINITY
    cpu_set_t allowed; CPU_ZERO(&allowed); CPU_SET(0,&allowed);
    if(sched_setaffinity(0,sizeof(allowed),&allowed)){perror("CPU0 affinity");return 6;}
#endif
    if(argc!=8){fprintf(stderr,"Usage: tracking_probe rate exact.c128 control.c128 dwell.ci16 refresh_interval radius fallback\n");return 2;}
    char *end; errno=0; unsigned long rate=strtoul(argv[1],&end,10);
    if(errno||*end||(rate!=2500000&&rate!=5000000&&rate!=7500000&&rate!=10000000))return 2;
    long refresh=strtol(argv[5],&end,10); if(*end||(refresh!=1&&refresh!=2&&refresh!=3&&refresh!=5&&refresh!=11))return 2;
    long radius=strtol(argv[6],&end,10); if(*end||(radius!=0&&radius!=1))return 2;
    long fallback=strtol(argv[7],&end,10); if(*end||(fallback!=0&&fallback!=1))return 2;
    size_t frame=(rate+375)/750,dwell=rate*120/1000,probe=rate/50,stride=rate/100;
    leo_presence_complex *exact=read_all(argv[2],frame,sizeof(*exact));
    leo_presence_complex *control=read_all(argv[3],frame,sizeof(*control));
    short *ci16=read_all(argv[4],dwell*4,sizeof(*ci16));
    if(!exact||!control||!ci16){fprintf(stderr,"Invalid input file\n");return 2;}
    leo_tracking_workspace *workspace=leo_tracking_create((uint32_t)rate,exact,control,frame);
    leo_presence_complex *samples=calloc(probe,sizeof(*samples));
    if(!workspace||!samples)return 3;
    leo_tracking_state states[RECEIVERS]={0};
    int refresh_count=0,tracked_count=0,fallback_count=0,total_attempts=0;
    double total_cpu=0;
    printf("{\"type\":\"context\",\"schema\":\"leo-glrt-tracking/v1\","
        "\"rate_hz\":%lu,\"windows\":%d,\"receivers\":%d,"
        "\"refresh_interval\":%ld,\"radius\":%ld,\"fallback_enabled\":%s}\n",
        rate,WINDOWS,RECEIVERS,refresh,radius,fallback?"true":"false");
    for(int window=0;window<WINDOWS;++window)for(int rx=0;rx<RECEIVERS;++rx){
        for(size_t i=0;i<probe;++i){size_t at=((size_t)window*stride+i)*4+(size_t)rx*2;
            samples[i]=(leo_presence_complex){ci16[at],ci16[at+1]};}
        leo_tracking_result result={0}; int use_refresh=window==0||window%refresh==0;
        int rc=use_refresh?leo_tracking_refresh(workspace,samples,probe,&states[rx],&result):
            leo_tracking_follow(workspace,samples,probe,&states[rx],(int)radius,&result);
        const char *mode=use_refresh?"refresh":"tracked"; int did_fallback=0;
        if(!rc&&!use_refresh&&fallback&&result.positive_count==0){
            leo_tracking_result attempted=result,refreshed={0};
            rc=leo_tracking_refresh(workspace,samples,probe,&states[rx],&refreshed);
            if(!rc){result=refreshed;add_cost(&result,&attempted);mode="fallback";did_fallback=1;}
        }
        if(rc){
            emit_error(rx,window,"tracking_run_failed");
            for(int tail=window*RECEIVERS+rx+1;tail<WINDOWS*RECEIVERS;++tail)
                emit_error(tail%RECEIVERS,tail/RECEIVERS,"aborted_after_failure");
            return 4;
        }
        if(use_refresh)++refresh_count;else ++tracked_count;
        if(did_fallback)++fallback_count;
        total_attempts+=result.candidate_eval_attempts;total_cpu+=result.total_cpu_ms;
        emit_result(rx,window,mode,did_fallback,&result);
    }
    printf("{\"type\":\"summary\",\"status\":\"ok\",\"refresh_windows\":%d,"
        "\"tracked_windows\":%d,\"fallback_windows\":%d,"
        "\"candidate_eval_attempts\":%d,\"total_cpu_ms\":%.17g}\n",
        refresh_count,tracked_count,fallback_count,total_attempts,total_cpu);
    leo_tracking_destroy(workspace);free(samples);free(ci16);free(control);free(exact);return 0;
}
