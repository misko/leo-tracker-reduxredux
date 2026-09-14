/* Bounded saved-IQ benchmark. No device, network or production control API. */
#define _POSIX_C_SOURCE 200809L
#include "../src/leo/analysis/native_presence/progressive_decision.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>

int main(int argc,char **argv)
{
    if (argc!=2) return 2;
    char *end; double budget=strtod(argv[1],&end);
    if (!*argv[1] || *end || budget<0 || budget>1000) return 2;
    alarm(100);
    struct rlimit cpu={85,85},memory={160*1024*1024,160*1024*1024};
    if (setrlimit(RLIMIT_CPU,&cpu)) return 2;
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    (void)memory;
#endif
    uint32_t header[4];
    if (fread(header,4,4,stdin)!=4 || memcmp(header,"LPG1",4) || header[1]!=5000000 ||
        header[2]!=6667 || !header[3] || header[3]>64) return 2;
    size_t n=header[2];
    float taps[129];
    leo_presence_complex *templates=malloc(4*n*sizeof(*templates));
    int16_t *iq=malloc(1200000*4);
    int16_t *reference=malloc(100000*4),*filtered=malloc(100000*4);
    leo_progressive_workspace *w[2]={NULL,NULL};
    int status=2;
    if (!templates || !iq || !reference || !filtered || fread(taps,4,129,stdin)!=129 ||
        fread(templates,sizeof(*templates),4*n,stdin)!=4*n) goto done;
    for (unsigned e=0;e<2;++e) {
        w[e]=leo_progressive_create(templates+2*e*n,templates+(2*e+1)*n,n,taps);
        if (!w[e]) goto done;
    }
    for (unsigned j=0;j<header[3];++j) {
        uint32_t h[4]; leo_progressive_result r;
        if (fread(h,4,4,stdin)!=4 || h[1]>1 || h[2]>1 ||
            fread(iq,4,1200000,stdin)!=1200000 || fread(reference,4,100000,stdin)!=100000 ||
            leo_progressive_filter(iq,1200000,0,taps,filtered)) goto done;
        unsigned changed=0,max_error=0;
        for (unsigned k=0;k<200000;++k) {
            unsigned error=(unsigned)abs((int)reference[k]-(int)filtered[k]);
            changed+=error!=0;
            if (error>max_error) max_error=error;
        }
        if (max_error>1 || leo_progressive_run(w[h[2]],iq,1200000,budget,&r)) goto done;
        printf("{\"case\":%u,\"rx\":%u,\"edge\":%u,\"visit\":%u,"
            "\"probes\":%u,\"mask\":%u,\"positive_mask\":%u,\"outcome\":%u,"
            "\"budget_exceeded\":%u,\"filter_cpu_ms\":%.9g,\"confirm_cpu_ms\":%.9g,"
            "\"cpu_ms\":%.9g,\"wall_ms\":%.9g,\"filter_max_error_lsb\":%u,"
            "\"filter_changed_components\":%u}\n",
            h[0],h[1],h[2],h[3],r.probes,r.mask,r.positive_mask,r.outcome,
            r.budget_exceeded,r.filter_cpu_ms,r.confirm_cpu_ms,r.total_cpu_ms,r.total_wall_ms,
            max_error,changed);
        fflush(stdout);
    }
    if (fgetc(stdin)!=EOF || ferror(stdin)) goto done;
    status=0;
done:
    for (unsigned e=0;e<2;++e) leo_progressive_destroy(w[e]);
    free(templates); free(iq); free(reference); free(filtered); return status;
}
