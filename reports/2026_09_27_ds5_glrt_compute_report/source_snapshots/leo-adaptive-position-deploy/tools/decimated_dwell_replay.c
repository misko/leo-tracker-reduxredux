/* Bounded saved-data qualification tool. No IIO, RF, or service control. */
#define _POSIX_C_SOURCE 200809L
#include "../src/leo/analysis/native_presence/decision_decimator.h"
#include "../src/leo/analysis/native_presence/dwell.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
static double now(clockid_t id)
{ struct timespec t; clock_gettime(id,&t); return t.tv_sec*1000.0+t.tv_nsec/1e6; }
int main(void)
{
    alarm(100);
    struct rlimit cpu={85,85}, memory={160*1024*1024,160*1024*1024};
    if (setrlimit(RLIMIT_CPU,&cpu)) return 2;
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    (void)memory;
#endif
    uint32_t header[6];
    if (fread(header,4,6,stdin)!=6 || (memcmp(header,"LDD1",4) && memcmp(header,"LDR1",4)) || header[1]!=2500000 ||
        header[2]!=3333 || !header[3] || header[3]>64 || header[4]>257 || header[5]>257) return 2;
    int16_t h1[257],h2[257]; float denominator[8]; size_t n=header[2];
    int recursive=!memcmp(header,"LDR1",4);
    leo_presence_complex *templates=malloc(4*n*sizeof(*templates));
    int16_t *iq=malloc(4800000), *filtered=malloc(1200000),*reference=malloc(1200000);
    leo_decimator *filter=NULL; leo_presence_dwell_workspace *w[2]={NULL,NULL};
    int status=2;
    if (!templates || !iq || !filtered || !reference ||
        fread(h1,2,header[4],stdin)!=header[4] || fread(h2,2,header[5],stdin)!=header[5] ||
        (recursive && fread(denominator,4,8,stdin)!=8) ||
        fread(templates,sizeof(*templates),4*n,stdin)!=4*n) goto done;
    filter=recursive ? leo_decimator_create_recursive(h1,header[4],h2,header[5],denominator,1200000) :
        leo_decimator_create(h1,header[4],h2,header[5],1200000);
    if (!filter) goto done;
    for (unsigned e=0;e<2;++e) {
        w[e]=leo_presence_dwell_create(2500000,templates+2*e*n,templates+(2*e+1)*n,n,512);
        if (!w[e]) goto done;
    }
    for (unsigned j=0;j<header[3];++j) {
        uint32_t h[4]; leo_presence_dwell_result r;
        if (fread(h,4,4,stdin)!=4 || h[1]>1 || h[2]>1 ||
            fread(iq,4,1200000,stdin)!=1200000 || fread(reference,4,300000,stdin)!=300000) goto done;
        double start=now(CLOCK_PROCESS_CPUTIME_ID), wall=now(CLOCK_MONOTONIC);
        if (leo_decimator_run(filter,iq,1200000,filtered)) goto done;
        double filtered_at=now(CLOCK_PROCESS_CPUTIME_ID);
        if (leo_presence_dwell_run_ci16(w[h[2]],filtered,300000,1,0,&r)) goto done;
        double total=now(CLOCK_PROCESS_CPUTIME_ID)-start, elapsed=now(CLOCK_MONOTONIC)-wall;
        unsigned max_error=0,changed=0;
        for (unsigned k=0;k<600000;++k) {
            unsigned error=(unsigned)abs((int)filtered[k]-reference[k]);
            if (error>max_error) max_error=error;
            changed+=error!=0;
        }
#if defined(LEO_DECIMATOR_FP32) || defined(LEO_DECIMATOR_FFT)
        if (max_error>2) goto done;
#else
        if (max_error>(recursive ? 2u : 0u)) {
            fprintf(stderr,"case %u filter maximum error %u LSB\n",h[0],max_error); goto done;
        }
#endif
        unsigned positive=0;
        const leo_presence_result *c=&r.confirmations[0];
        for (int k=0;k<c->candidate_count;++k)
            positive|=c->candidates[k].fractional_complete && c->candidates[k].exact_score>=.175 &&
                c->candidates[k].margin>=.025;
        printf("{\"case\":%u,\"rx\":%u,\"edge\":%u,\"visit\":%u,\"positive\":%u,"
            "\"confirmation_mask\":%u,\"filter_cpu_ms\":%.9g,\"worker_cpu_ms\":%.9g,"
            "\"cpu_ms\":%.9g,\"wall_ms\":%.9g,\"filter_max_error_lsb\":%u,"
            "\"filter_changed_components\":%u,\"candidate_count\":%d,"
            "\"exact_score\":%.17g,\"margin\":%.17g,\"epoch\":%d,"
            "\"fractional_offset_samples\":%.17g,\"acquired_cfo_hz\":%.17g}\n",
            h[0],h[1],h[2],h[3],positive,r.confirmation_window_mask,filtered_at-start,
            r.total_cpu_ms,total,elapsed,max_error,changed,c->candidate_count,
            c->candidates[0].exact_score,c->candidates[0].margin,c->candidates[0].epoch,
            c->candidates[0].fractional_offset_samples,c->candidates[0].acquired_cfo_hz);
        fflush(stdout);
    }
    if (fgetc(stdin)!=EOF || ferror(stdin)) goto done;
    status=0;
done:
    for (unsigned e=0;e<2;++e) leo_presence_dwell_destroy(w[e]);
    leo_decimator_destroy(filter); free(templates);free(iq);free(filtered);free(reference);
    return status;
}
