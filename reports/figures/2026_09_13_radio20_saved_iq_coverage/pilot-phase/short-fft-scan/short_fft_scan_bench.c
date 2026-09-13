/* Saved input only: measure two-thread coarse search plus bounded ranking. */
#define main original_bench_main
#include "/home/mouse9911/gits/plutosdr-fw-radio20-tracking/tools/glrt_cpu_tracking_bench.c"
#undef main
#include <math.h>
int main(int argc,char **argv)
{
    struct glrt_cpu_coarse_workspace *w=calloc(1,sizeof(*w));
    int16_t *iq=malloc(RETAINED*4U),*refs=malloc(105600),bank[12][11][11][2];
    struct glrt_cpu_coarse_peak peaks[64];struct context ctx={0};uint32_t count;
    fftw_complex *bins=fftw_malloc(GLRT_RESOLVER_FFT*sizeof(*bins));
    unsigned budget,rank_fft,best=0;double scores[64]={0},energy=0;
    uint64_t begin,grid_done,selected,ranked;
    alarm(15);
    if(argc!=6 || !w || !iq || !refs || !bins || load(argv[1],bank,sizeof(bank)) ||
       load(argv[2],iq,RETAINED*4U) || load(argv[3],refs,105600)) return 2;
    rank_fft=(unsigned)strtoul(argv[5],NULL,10);
    if(rank_fft!=4096 && rank_fft!=8192 && rank_fft!=16384) return 2;
    budget=(unsigned)strtoul(argv[4],NULL,10);if(budget!=8 && budget!=64) return 2;
    ctx.fft=fftw_plan_dft_1d(rank_fft,bins,bins,FFTW_FORWARD,FFTW_ESTIMATE|FFTW_UNALIGNED);
    if(!ctx.fft) return 2;
    ctx.deadline=clock_ns(NULL)+UINT64_C(10000000000);
    for(unsigned n=0;n<3300;n++) energy+=(double)refs[4*n]*refs[4*n]+(double)refs[4*n+1]*refs[4*n+1];
    begin=clock_ns(NULL);
    /* Search includes the legacy eight selection, reported explicitly below. */
    if(search(w,iq,bank,&ctx)) return 2;
    grid_done=clock_ns(NULL);
    if(glrt_cpu_coarse_select_bounded(w,peaks,budget,&count,cancelled,&ctx) || count!=budget) return 2;
    selected=clock_ns(NULL);
    for(unsigned k=0;k<count;k++) {
        double observed=0;unsigned first=peaks[k].epoch+22;
        if(cancelled(&ctx)) return 2;
        memset(bins,0,GLRT_RESOLVER_FFT*sizeof(*bins));
        for(unsigned n=0;n<3300;n++) {
            double i=iq[2*(first+n)],q=iq[2*(first+n)+1],ri=refs[4*n],rq=refs[4*n+1];
            bins[n][0]=i*ri+q*rq;bins[n][1]=q*ri-i*rq;observed+=i*i+q*q;
        }
        fftw_execute(ctx.fft);
        for(unsigned n=0;n<rank_fft;n++) {
            double p=(bins[n][0]*bins[n][0]+bins[n][1]*bins[n][1])/fmax(observed*energy,1);
            if(p>scores[k]) scores[k]=p;
        }
        if(scores[k]>scores[best]) best=k;
    }
    if(cancelled(&ctx)) return 2;
    ranked=clock_ns(NULL);
    for(unsigned k=0;k<count;k++) printf("{\"kind\":\"peak\",\"epoch\":%u,\"frequency\":%u,\"score\":%u,\"rank_power\":%.17g}\n",peaks[k].epoch,peaks[k].frequency,peaks[k].score,scores[k]);
    printf("{\"kind\":\"timing\",\"budget\":%u,\"winner\":%u,\"grid_and_legacy_select_ns\":%llu,\"bounded_select_ns\":%llu,\"ranking_ns\":%llu,\"total_ns\":%llu}\n",budget,best+1,(unsigned long long)(grid_done-begin),(unsigned long long)(selected-grid_done),(unsigned long long)(ranked-selected),(unsigned long long)(ranked-begin));
    fftw_destroy_plan(ctx.fft);fftw_free(bins);free(w);free(iq);free(refs);
    return fflush(stdout)!=0;
}
