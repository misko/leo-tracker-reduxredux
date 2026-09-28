#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <sched.h>
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "dwell.h"
#include "fft.h"
#if PROBE_ALIGNED
#include "blind_aligned_v5.h"
#endif

#ifndef PROBE_METHOD
#error "PROBE_METHOD must name the immutable build method"
#endif

typedef struct { void *data; size_t size; int fd; } mapped_file;

static double millis(clockid_t id)
{
    struct timespec value;
    if (clock_gettime(id,&value)) { perror("clock_gettime"); exit(2); }
    return 1000.0*value.tv_sec+1e-6*value.tv_nsec;
}

static int map_read(const char *path, mapped_file *out)
{
    struct stat status;
    memset(out,0,sizeof(*out)); out->fd=-1;
    out->fd=open(path,O_RDONLY);
    if (out->fd<0 || fstat(out->fd,&status) || status.st_size<=0) return -1;
    out->size=(size_t)status.st_size;
    out->data=mmap(NULL,out->size,PROT_READ,MAP_PRIVATE,out->fd,0);
    return out->data==MAP_FAILED ? -1 : 0;
}

static void unmap_file(mapped_file *file)
{
    if (file->data && file->data!=MAP_FAILED) munmap(file->data,file->size);
    if (file->fd>=0) close(file->fd);
}

static void json_candidate(const leo_presence_candidate *c)
{
    printf("{\"epoch\":%d,\"fractional_complete\":%d,",c->epoch,c->fractional_complete);
    printf("\"acquired_cfo_hz\":%.17g,\"fractional_offset_samples\":%.17g,",c->acquired_cfo_hz,c->fractional_offset_samples);
    printf("\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g,",c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
    printf("\"acquire_score\":%.17g,\"verify_score\":%.17g,\"verify_control_score\":%.17g,\"conditioned_score\":%.17g,\"coarse_score\":%.17g,",c->acquire_score,c->verify_score,c->verify_control_score,c->conditioned_score,c->coarse_score);
    printf("\"exact_grid\":["); for (int k=0;k<5;++k) printf("%s%.17g",k?",":"",c->exact_grid[k]);
    printf("],\"control_grid\":["); for (int k=0;k<5;++k) printf("%s%.17g",k?",":"",c->control_grid[k]);
    printf("]}");
}

static void json_presence(const leo_presence_result *p)
{
    printf("{\"candidate_count\":%d,\"candidates\":[",p->candidate_count);
    int n=p->candidate_count; if (n<0) n=0; if (n>2) n=2;
    for (int k=0;k<n;++k) { if(k) putchar(','); json_candidate(&p->candidates[k]); }
    printf("],\"conversion_cpu_ms\":%.17g,\"coarse_cpu_ms\":%.17g,\"fine_cpu_ms\":%.17g,\"fractional_cpu_ms\":%.17g,\"total_cpu_ms\":%.17g,\"total_wall_ms\":%.17g}",p->conversion_cpu_ms,p->coarse_cpu_ms,p->fine_cpu_ms,p->fractional_cpu_ms,p->total_cpu_ms,p->total_wall_ms);
}

static void json_profile(const leo_presence_profile *p)
{
    printf("{\"acquisition_fft_cpu_ms\":%.17g,\"conditioned_cpu_ms\":%.17g,\"verification_cpu_ms\":%.17g,\"epoch_lattice_cpu_ms\":%.17g,\"final_confirmation_cpu_ms\":%.17g,\"local_coarse_cpu_ms\":%.17g,\"coarse_frames\":%u,\"fine_frames\":%u,\"epoch_frames\":%u,\"anchor_stride\":%u,\"epoch_stride\":%u,\"conditioned_radius_hz\":%u}",p->acquisition_fft_cpu_ms,p->conditioned_cpu_ms,p->verification_cpu_ms,p->epoch_lattice_cpu_ms,p->final_confirmation_cpu_ms,p->local_coarse_cpu_ms,p->coarse_frames,p->fine_frames,p->epoch_frames,p->anchor_stride,p->epoch_stride,p->conditioned_radius_hz);
}

static void json_glrt_profile(const leo_presence_glrt_profile *p)
{
    printf("{\"rotation_prelude_cpu_ms\":%.17g,\"frame_interpolation_correlation_cpu_ms\":%.17g,\"frame_ceiling_short_fft_cpu_ms\":%.17g,\"post_fft_cpu_ms\":%.17g,\"calls\":%u,\"frames\":%u}",p->rotation_prelude_cpu_ms,p->frame_interpolation_correlation_cpu_ms,p->frame_ceiling_short_fft_cpu_ms,p->post_fft_cpu_ms,p->calls,p->frames);
}

static void json_screens(const leo_presence_rank_screens *s)
{
    printf("{\"available_mask\":%u,\"selected\":%u,\"scores\":[",s->available_mask,s->selected);
    for(int row=0;row<2;++row) {
        printf("%s[",row?",":"");
        for(int k=0;k<6;++k) printf("%s%.17g",k?",":"",s->scores[row][k]);
        putchar(']');
    }
    printf("],\"contrast\":[%.17g,%.17g],\"order\":[",s->contrast[0],s->contrast[1]);
    for(int row=0;row<2;++row) { printf("%s[",row?",":""); for(int k=0;k<6;++k) printf("%s%u",k?",":"",s->order[row][k]); putchar(']'); }
    printf("],\"epochs\":[");
    for(int row=0;row<2;++row) { printf("%s[",row?",":""); for(int k=0;k<6;++k) printf("%s%u",k?",":"",s->epochs[row][k]); putchar(']'); }
    printf("]}");
}

static void json_dwell(const leo_presence_dwell_result *d)
{
    printf("{\"rank\":{\"scores\":[");
    for (int k=0;k<6;++k) printf("%s%.17g",k?",":"",d->rank.scores[k]);
    printf("],\"order\":["); for(int k=0;k<6;++k) printf("%s%u",k?",":"",d->rank.order[k]);
    printf("],\"projected_epoch_samples\":["); for(int k=0;k<6;++k) printf("%s%u",k?",":"",d->rank.projected_epoch_samples[k]);
    printf("],\"fold_cpu_ms\":%.17g,\"correlation_cpu_ms\":%.17g,\"total_cpu_ms\":%.17g,\"total_wall_ms\":%.17g},",d->rank.fold_cpu_ms,d->rank.correlation_cpu_ms,d->rank.total_cpu_ms,d->rank.total_wall_ms);
    printf("\"confirmation_count\":%u,\"confirmation_window_mask\":%u,\"confirmations\":[",d->confirmation_count,d->confirmation_window_mask);
    for (uint32_t k=0;k<d->confirmation_count && k<6;++k) {
        if(k) putchar(',');
        json_presence(&d->confirmations[k]);
    }
    printf("],\"nuisances\":[");
    for (uint32_t k=0;k<d->confirmation_count && k<6;++k) {
        const leo_presence_nuisance *n=&d->nuisances[k];
        printf("%s{\"enabled\":%d,\"applied\":%d,\"frequency_hz\":%.17g,\"spectral_fraction\":%.17g,\"fitted_power_fraction\":%.17g,\"cpu_ms\":%.17g}",k?",":"",n->enabled,n->applied,n->frequency_hz,n->spectral_fraction,n->fitted_power_fraction,n->cpu_ms);
    }
    printf("],\"prefix_cpu_ms\":["); for(uint32_t k=0;k<d->confirmation_count && k<6;++k) printf("%s%.17g",k?",":"",d->prefix_cpu_ms[k]);
    printf("],\"prefix_wall_ms\":["); for(uint32_t k=0;k<d->confirmation_count && k<6;++k) printf("%s%.17g",k?",":"",d->prefix_wall_ms[k]);
    printf("],\"timing_proposals\":[");
    for(uint32_t k=0;k<d->confirmation_count && k<6;++k) {
        const leo_presence_timing_proposal *p=&d->timing_proposals[k];
        printf("%s{\"epoch\":%u,\"score\":%.17g,\"fold_cpu_ms\":%.17g,\"correlation_cpu_ms\":%.17g,\"total_cpu_ms\":%.17g,\"total_wall_ms\":%.17g}",k?",":"",p->epoch,p->score,p->fold_cpu_ms,p->correlation_cpu_ms,p->total_cpu_ms,p->total_wall_ms);
    }
    printf("],\"total_cpu_ms\":%.17g,\"total_wall_ms\":%.17g}",d->total_cpu_ms,d->total_wall_ms);
}

typedef struct {
#if PROBE_ALIGNED
    leo_blind_aligned_v5_workspace *work[2];
#else
    leo_presence_dwell_workspace *work[2];
    int16_t *packed;
#endif
} probe_work;

static int run_rx(probe_work *w, const int16_t *raw, size_t count, uint32_t rx,
    leo_presence_dwell_result *result, leo_presence_rank_screens *screens,
    double *pack_cpu, double *pack_wall,
    double *call_cpu, double *call_wall)
{
    double c0=millis(CLOCK_PROCESS_CPUTIME_ID),w0=millis(CLOCK_MONOTONIC);
#if PROBE_ALIGNED
    *pack_cpu=0; *pack_wall=0;
    int rc=leo_blind_aligned_v5_run_ci16(w->work[rx],raw,count,rx,1,0,result);
    *call_cpu=millis(CLOCK_PROCESS_CPUTIME_ID)-c0;
    *call_wall=millis(CLOCK_MONOTONIC)-w0;
    return rc ? rc : leo_blind_aligned_v5_get_screens(w->work[rx],screens);
#else
    for (size_t k=0;k<count;++k) {
        w->packed[2*k]=raw[4*k+2*rx];
        w->packed[2*k+1]=raw[4*k+2*rx+1];
    }
    *pack_cpu=millis(CLOCK_PROCESS_CPUTIME_ID)-c0;
    *pack_wall=millis(CLOCK_MONOTONIC)-w0;
    c0=millis(CLOCK_PROCESS_CPUTIME_ID); w0=millis(CLOCK_MONOTONIC);
    int rc=leo_presence_dwell_run_ci16(w->work[rx],w->packed,count,1,0,result);
    *call_cpu=millis(CLOCK_PROCESS_CPUTIME_ID)-c0;
    *call_wall=millis(CLOCK_MONOTONIC)-w0;
    return rc ? rc : leo_presence_dwell_get_screens(w->work[rx],screens);
#endif
}

int main(int argc, char **argv)
{
    alarm(15);
    cpu_set_t allowed, chosen;
    if (sched_getaffinity(0,sizeof(allowed),&allowed)) return 2;
    int core=-1;
    for(int i=0;i<CPU_SETSIZE;++i) if(CPU_ISSET(i,&allowed)) { core=i; break; }
    if(core<0) return 2;
    CPU_ZERO(&chosen); CPU_SET(core,&chosen);
    if(sched_setaffinity(0,sizeof(chosen),&chosen)) return 2;
    if(sched_getaffinity(0,sizeof(allowed),&allowed) || CPU_COUNT(&allowed)!=1 || !CPU_ISSET(core,&allowed)) return 2;
    fprintf(stderr,"single_core=%d pid=%ld\n",core,(long)getpid());
    if (argc!=7) {
        fprintf(stderr,"usage: %s RAW EXACT CONTROL RATE EDGE CASE_ID\n",argv[0]); return 2;
    }
    char *end=NULL; unsigned long rate=strtoul(argv[4],&end,10);
    if (!end || *end || (rate!=2500000 && rate!=5000000 && rate!=7500000 && rate!=10000000) ||
        (strcmp(argv[5],"lower") && strcmp(argv[5],"upper"))) return 2;
    for (const char *p=argv[6];*p;++p) if (!( (*p>='a'&&*p<='z')||(*p>='A'&&*p<='Z')||(*p>='0'&&*p<='9')||*p=='-'||*p=='_' )) return 2;
    double io_c=millis(CLOCK_PROCESS_CPUTIME_ID),io_w=millis(CLOCK_MONOTONIC);
    mapped_file raw={0},exact={0},control={0};
    if (map_read(argv[1],&raw)||map_read(argv[2],&exact)||map_read(argv[3],&control)) { perror("map"); return 2; }
    volatile uint8_t touch=0; const uint8_t *rb=raw.data,*eb=exact.data,*cb=control.data;
    for(size_t k=0;k<raw.size;k+=4096) touch^=rb[k];
    for(size_t k=0;k<exact.size;k+=4096) touch^=eb[k];
    for(size_t k=0;k<control.size;k+=4096) touch^=cb[k];
    (void)touch;
    io_c=millis(CLOCK_PROCESS_CPUTIME_ID)-io_c; io_w=millis(CLOCK_MONOTONIC)-io_w;
    size_t count=(size_t)rate*120/1000, template_count=exact.size/sizeof(leo_presence_complex);
    if (raw.size!=count*4*sizeof(int16_t) || exact.size!=control.size || exact.size%sizeof(leo_presence_complex)) return 2;
    double init_c=millis(CLOCK_PROCESS_CPUTIME_ID),init_w=millis(CLOCK_MONOTONIC);
    probe_work work={0};
    for(int rx=0;rx<2;++rx) {
#if PROBE_ALIGNED
        work.work[rx]=leo_blind_aligned_v5_create((uint32_t)rate,exact.data,control.data,template_count,512,0);
#else
        work.work[rx]=leo_presence_dwell_create((uint32_t)rate,exact.data,control.data,template_count,512);
#endif
        if(!work.work[rx]) { fprintf(stderr,"workspace init failed\n"); return 2; }
    }
#if !PROBE_ALIGNED
    work.packed=malloc(count*2*sizeof(int16_t)); if(!work.packed) return 2;
#endif
    init_c=millis(CLOCK_PROCESS_CPUTIME_ID)-init_c; init_w=millis(CLOCK_MONOTONIC)-init_w;
    for (int warm=0;warm<1;++warm) for(uint32_t rx=0;rx<2;++rx) {
        leo_presence_dwell_result d={0}; leo_presence_rank_screens s={0}; double a,b,c,e;
        if(run_rx(&work,raw.data,count,rx,&d,&s,&a,&b,&c,&e)) return 2;
    }
    printf("{\"schema\":\"org.leo.research.arm-stateless-probe-result/v1\",\"method\":\"%s\",\"fft_backend\":\"%s\",\"case_id\":\"%s\",\"rate_hz\":%lu,\"edge\":\"%s\",\"io_cpu_ms\":%.17g,\"io_wall_ms\":%.17g,\"initialization_cpu_ms\":%.17g,\"initialization_wall_ms\":%.17g,\"warmups\":1,\"repetitions\":[",PROBE_METHOD,leo_fft_backend_identity(),argv[6],rate,argv[5],io_c,io_w,init_c,init_w);
    for(int rep=0;rep<5;++rep) {
        double vc0=millis(CLOCK_PROCESS_CPUTIME_ID),vw0=millis(CLOCK_MONOTONIC);
        leo_presence_dwell_result results[2]={0};
        leo_presence_rank_screens screens[2]={0};
        leo_presence_profile profiles[2]={0};
        leo_presence_glrt_profile glrt_profiles[2]={0};
        double pc[2],pw[2],dc[2],dw[2];
        for(uint32_t rx=0;rx<2;++rx)
            if(run_rx(&work,raw.data,count,rx,&results[rx],&screens[rx],&pc[rx],&pw[rx],&dc[rx],&dw[rx])) return 2;
        double visit_cpu=millis(CLOCK_PROCESS_CPUTIME_ID)-vc0;
        double visit_wall=millis(CLOCK_MONOTONIC)-vw0;
#if PROBE_ALIGNED
        for(uint32_t rx=0;rx<2;++rx)
            if(leo_blind_aligned_v5_get_profile(work.work[rx],&profiles[rx])) return 2;
        for(uint32_t rx=0;rx<2;++rx)
            if(leo_blind_aligned_v5_get_glrt_profile(work.work[rx],&glrt_profiles[rx])) return 2;
#endif
        if(rep) putchar(',');
        printf("{\"index\":%d,\"receivers\":[",rep);
        for(uint32_t rx=0;rx<2;++rx) {
            printf("%s{\"receiver\":%u,\"packing_cpu_ms\":%.17g,\"packing_wall_ms\":%.17g,\"detector_cpu_ms\":%.17g,\"detector_wall_ms\":%.17g,\"result\":",rx?",":"",rx,pc[rx],pw[rx],dc[rx],dw[rx]);
            json_dwell(&results[rx]); printf(",\"screens\":"); json_screens(&screens[rx]);
            printf(",\"profile\":"); json_profile(&profiles[rx]);
            printf(",\"glrt_profile\":"); json_glrt_profile(&glrt_profiles[rx]); putchar('}');
        }
        printf("],\"visit_cpu_ms\":%.17g,\"visit_wall_ms\":%.17g}",visit_cpu,visit_wall);
    }
    printf("]}\n");
#if PROBE_ALIGNED
    for(int rx=0;rx<2;++rx) leo_blind_aligned_v5_destroy(work.work[rx]);
#else
    for(int rx=0;rx<2;++rx) leo_presence_dwell_destroy(work.work[rx]);
    free(work.packed);
#endif
    unmap_file(&raw); unmap_file(&exact); unmap_file(&control);
    return 0;
}
