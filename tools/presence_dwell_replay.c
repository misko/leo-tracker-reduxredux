/* Saved-IQ full-dwell execution only. Never opens IIO, radio nodes, or sockets. */
#define _POSIX_C_SOURCE 200809L
#include "../src/leo/analysis/native_presence/dwell.h"
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <unistd.h>

static uint32_t u32(const unsigned char *p)
{ return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24; }
static uint64_t u64(const unsigned char *p)
{ return u32(p)|(uint64_t)u32(p+4)<<32; }
static int argument(const char *text, unsigned long low, unsigned long high, uint32_t *out)
{
    char *end;
    unsigned long value=strtoul(text,&end,10);
    if (!*text || *end || value<low || value>high) return -1;
    *out=(uint32_t)value;
    return 0;
}
static void doubles(const double *values, size_t count)
{
    putchar('[');
    for (size_t k=0; k<count; ++k) printf("%s%.17g",k ? "," : "",values[k]);
    putchar(']');
}
static void integers(const uint32_t *values, size_t count)
{
    putchar('[');
    for (size_t k=0; k<count; ++k) printf("%s%u",k ? "," : "",values[k]);
    putchar(']');
}

int main(int argc, char **argv)
{
    /* PROBE.rank TEMPLATES BINS MAX_CONFIRMATIONS blind|seeded ITERATIONS */
    uint32_t bins, maximum, repeats, timing_bins=0;
    if ((argc!=7 && argc!=8) || argument(argv[3],512,8192,&bins) || (bins&(bins-1)) ||
        argument(argv[4],1,6,&maximum) || argument(argv[6],1,20,&repeats) ||
        (strcmp(argv[5],"blind") && strcmp(argv[5],"seeded")) ||
        (argc==8 && (argument(argv[7],512,8192,&timing_bins) || (timing_bins&(timing_bins-1))))) return 2;
    uint32_t seeded=!strcmp(argv[5],"seeded");
    uint16_t endian=1;
    if (*(unsigned char *)&endian!=1 || sizeof(double)!=8 || sizeof(leo_presence_complex)!=16) return 2;
    alarm(45);
    struct rlimit cpu={35,35}, memory={128*1024*1024,128*1024*1024};
    if (setrlimit(RLIMIT_CPU,&cpu)) return 2;
#if !defined(__SANITIZE_ADDRESS__)
    if (setrlimit(RLIMIT_AS,&memory)) return 2;
#else
    (void)memory;
#endif
    FILE *input=fopen(argv[1],"rb"), *templates=fopen(argv[2],"rb");
    int status=2;
    leo_presence_complex *exact=NULL, *package=NULL;
    int16_t *iq=NULL;
    leo_presence_dwell_workspace *workspace=NULL;
    unsigned char header[28], template_header[12];
    if (!input || !templates || fread(header,1,28,input)!=28 ||
        fread(template_header,1,12,templates)!=12) goto done;
    uint32_t rate=u32(header+4), edge=u32(header+8), count=u32(header+12);
    uint64_t counter=u64(header+20);
    if (memcmp(header,"LRK1",4) || (rate!=2500000 && rate!=5000000) || edge>1 ||
        count!=rate/50*6 || u32(header+16)!=2 || counter>UINT64_MAX-count) goto done;
    size_t n=(rate+375)/750;
    if (memcmp(template_header,"LPT1",4) || u32(template_header+4)!=rate || u32(template_header+8)!=n) goto done;
    exact=malloc(n*sizeof(*exact)); package=malloc(4*n*sizeof(*package)); iq=malloc((size_t)count*4);
    if (!exact || !package || !iq || fread(exact,sizeof(*exact),n,input)!=n ||
        fread(iq,4,count,input)!=count || fgetc(input)!=EOF || ferror(input) ||
        fread(package,sizeof(*package),4*n,templates)!=4*n || fgetc(templates)!=EOF || ferror(templates) ||
        memcmp(exact,package+2*edge*n,n*sizeof(*exact))) goto done;
    workspace=timing_bins ? leo_presence_dwell_create_multires(rate,exact,package+(2*edge+1)*n,n,bins,timing_bins) :
        leo_presence_dwell_create(rate,exact,package+(2*edge+1)*n,n,bins);
    if (!workspace) goto done;
    for (uint32_t iteration=0; iteration<repeats; ++iteration) {
        leo_presence_dwell_result result;
        if (leo_presence_dwell_run_ci16(workspace,iq,count,maximum,seeded,&result)) goto done;
        printf("{\"rate_hz\":%u,\"edge\":%u,\"counter\":\"%" PRIu64
            "\",\"bins\":%u,\"timing_bins\":%u,\"mode\":\"%s\",\"iteration\":%u,\"rank\":{\"scores\":",
            rate,edge,counter,bins,timing_bins,argv[5],iteration);
        doubles(result.rank.scores,6);
        printf(",\"order\":"); integers(result.rank.order,6);
        printf(",\"projected_epoch_samples\":"); integers(result.rank.projected_epoch_samples,6);
        printf(",\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g},\"confirmation_count\":%u,\"confirmation_window_mask\":%u,\"confirmations\":[",
            result.rank.total_cpu_ms,result.rank.total_wall_ms,result.confirmation_count,result.confirmation_window_mask);
        for (uint32_t k=0; k<maximum; ++k) {
            const leo_presence_result *r=&result.confirmations[k];
            printf("%s{\"candidate_count\":%d,\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g,"
                "\"conversion_cpu_ms\":%.9g,\"coarse_cpu_ms\":%.9g,\"fine_cpu_ms\":%.9g,"
                "\"fractional_cpu_ms\":%.9g,\"candidates\":[",
                k ? "," : "",r->candidate_count,r->total_cpu_ms,r->total_wall_ms,
                r->conversion_cpu_ms,r->coarse_cpu_ms,r->fine_cpu_ms,r->fractional_cpu_ms);
            for (int j=0; j<r->candidate_count; ++j) {
                const leo_presence_candidate *c=&r->candidates[j];
                printf("%s{\"epoch\":%d,\"fractional_complete\":%d,\"acquired_cfo_hz\":%.17g,\"fractional_offset_samples\":%.17g,\"tracking_cfo_hz\":%.17g,\"exact_score\":%.17g,\"control_score\":%.17g,\"margin\":%.17g}",
                    j ? "," : "",c->epoch,c->fractional_complete,c->acquired_cfo_hz,c->fractional_offset_samples,
                    c->tracking_cfo_hz,c->exact_score,c->control_score,c->margin);
            }
            printf("]}");
        }
        printf("],\"nuisances\":[");
        for (uint32_t k=0; k<maximum; ++k) {
            const leo_presence_nuisance *nuisance=&result.nuisances[k];
            printf("%s{\"enabled\":%d,\"applied\":%d,\"frequency_hz\":%.17g,\"spectral_fraction\":%.17g,\"fitted_power_fraction\":%.17g}",
                k ? "," : "",nuisance->enabled,nuisance->applied,nuisance->frequency_hz,
                nuisance->spectral_fraction,nuisance->fitted_power_fraction);
        }
        printf("],\"prefix_cpu_ms\":"); doubles(result.prefix_cpu_ms,maximum);
        printf(",\"prefix_wall_ms\":"); doubles(result.prefix_wall_ms,maximum);
        printf(",\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g,\"timing_proposals\":[",result.total_cpu_ms,result.total_wall_ms);
        for (uint32_t k=0;k<maximum;++k) {
            const leo_presence_timing_proposal *t=&result.timing_proposals[k];
            printf("%s{\"epoch\":%u,\"score\":%.17g,\"total_cpu_ms\":%.9g,\"total_wall_ms\":%.9g}",k ? "," : "",t->epoch,t->score,t->total_cpu_ms,t->total_wall_ms);
        }
        printf("]}\n");
    }
    if (fflush(stdout) || ferror(stdout)) goto done;
    status=0;
done:
    leo_presence_dwell_destroy(workspace);
    free(exact); free(package); free(iq);
    if (input) fclose(input);
    if (templates) fclose(templates);
    return status;
}
