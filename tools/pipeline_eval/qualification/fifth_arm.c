/* Standalone offline stock and fifth-center wide detector plus the sealed scout. */
#define LEO_NATIVE_GLRT_SHORT_WINDOW_CLI 1
#define main leo_ordinary_cli_main
#include "native_glrt_cli.c"
#undef main
#undef _POSIX_C_SOURCE

#define main leo_differential_scout_cli_main
#include "differential_arm.c"
#undef main
#include "center_union.h"

static void signed_vector(const int32_t *values, size_t length)
{
    putchar('[');
    for (size_t i = 0; i < length; ++i) printf("%s%d", i ? "," : "", values[i]);
    putchar(']');
}

static void json_clock(stamp t)
{
    printf("{\"cpu_ns\":%" PRIu64 ",\"wall_ns\":%" PRIu64 "}",t.cpu,t.wall);
}

static void trace_lane(const leo_center_union_lane *lane)
{
    printf("{\"hint\":%d,\"added_epochs\":%d,\"active_epochs\":%d,\"ordinary\":",
        lane->hint,lane->added_epochs,lane->active_epochs);
    signed_vector(lane->ordinary,(size_t)lane->count);
    fputs(",\"stock_epochs\":",stdout);
    signed_vector(lane->stock_epochs,(size_t)lane->stock_epoch_count);
    fputs(",\"stock_peak_masks\":[",stdout);
    for (int i=0; i<lane->stock_epoch_count; ++i) printf("%s%u", i?",":"",lane->stock_peak_masks[i]);
    printf("],\"stock_peaks\":%d,\"extra_peaks\":%d,\"retained_stock\":%d,\"retained_extra\":%d}",
        lane->stock_peaks,lane->extra_peaks,lane->retained_stock,lane->retained_extra);
}

int main(int argc,char **argv)
{
    const uint16_t little = 1;
    if (argc != 8 || *(const uint8_t *)&little != 1 || DBL_MANT_DIG != 53 ||
        sizeof(int16_t)!=2 || sizeof(leo_native_glrt_complex)!=16 || sizeof(fftwf_complex)!=8) {
        fail("usage: fifth-arm stock|off|union iq.ci16 exact.c16 control.c16 filters.c8 energies.f64 repeats");
    }
    const int use_union=!strcmp(argv[1],"union"), off=!strcmp(argv[1],"off");
    if (!use_union && !off && strcmp(argv[1],"stock")) fail("unsupported detector mode");
    uint32_t repeats;
    if (number(argv[7],&repeats) || repeats<1 || repeats>4) fail("repetitions must be in [1,4]");

    const stamp started=clock_pair();
    int16_t *samples=read_array(argv[2],times*receivers*2u,sizeof(*samples));
    leo_native_glrt_complex *exact=read_array(argv[3],frame,sizeof(*exact));
    leo_native_glrt_complex *control=read_array(argv[4],frame,sizeof(*control));
    fftwf_complex *filters=NULL;
    double *energy=NULL,*scores=NULL;
    peak *ranking=NULL;
    if (use_union) {
        filters=read_array(argv[5],2u*branches*fft,sizeof(*filters));
        energy=read_array(argv[6],2u*frame,sizeof(*energy));
        scores=calloc(receivers*frame,sizeof(*scores));
        ranking=malloc(frame*sizeof(*ranking));
        if (!scores || !ranking) fail("unable to allocate proposal output");
        for (unsigned q=0; q<2u*branches*fft; ++q) {
            if (!isfinite(filters[q][0]) || !isfinite(filters[q][1])) fail("nonfinite scout filter");
        }
        for (unsigned q=0; q<2u*frame; ++q) {
            if (!isfinite(energy[q]) || energy[q]<=0) fail("invalid scout energy");
        }
    }
    const stamp loaded=clock_pair();
    leo_native_glrt *detector=NULL;
    if (leo_native_glrt_create_with_mode(&detector,10000000u,exact,control,frame,
            LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH)) fail("cannot initialize detector");
    const stamp detector_ready=clock_pair();
    scout_context *scout=use_union ? leo_differential_scout_create() : NULL;
    if (use_union && !scout) fail("cannot initialize differential FFTW scout");
    const stamp ready=clock_pair();

    leo_native_glrt_result result={0};
    leo_center_union_trace trace={0};
    int chosen[receivers][capacity]={{0}},counts[receivers]={0};
    int32_t hints[2]={-1,-1};
    stamp scouts[4],detectors[4];
    double native_cpu[4];
    for (unsigned q=0; q<repeats; ++q) {
        const stamp begin=clock_pair();
        if (scout) {
            leo_differential_scout(scout,samples,filters,energy,scores);
            for (int rx=0; rx<receivers; ++rx) {
                counts[rx]=rank_centers(scores+rx*frame,ranking,chosen[rx]);
                hints[rx]=counts[rx] ? chosen[rx][0] : -1;
            }
        }
        const stamp proposed=clock_pair();
        const int status=use_union||off ?
            leo_native_glrt_analyze_center_union_v1(detector,samples,times,hints,&result,&trace) :
            leo_native_glrt_analyze_short_window(detector,samples,times,&result);
        const stamp completed=clock_pair();
        if (status || result.row_count!=2) fail("full fractional detector failed");
        scouts[q]=elapsed(begin,proposed);
        detectors[q]=elapsed(proposed,completed);
        native_cpu[q]=result.detector_cpu_ms;
    }

    printf("{\"mode\":\"%s\",\"fftw_float_version\":\"%s\",\"read\":",argv[1],fftwf_version);
    json_clock(elapsed(started,loaded));
    fputs(",\"detector_context\":",stdout);
    json_clock(elapsed(loaded,detector_ready));
    fputs(",\"scout_context\":",stdout);
    json_clock(elapsed(detector_ready,ready));
    fputs(",\"calls\":[",stdout);
    for (unsigned q=0; q<repeats; ++q) {
        printf("%s{\"native_cpu_ms\":%.17g,\"scout\":",q?",":"",native_cpu[q]);
        json_clock(scouts[q]);
        fputs(",\"detector\":",stdout);
        json_clock(detectors[q]);
        putchar('}');
    }
    fputs("],\"top16\":[",stdout);
    for (int rx=0; rx<receivers; ++rx) {
        fputs(rx ? ",[" : "[",stdout);
        for (int i=0; i<counts[rx]; ++i) printf("%s%d",i?",":"",chosen[rx][i]);
        putchar(']');
    }
    fputs("],\"trace\":[",stdout);
    if (use_union||off) {
        trace_lane(&trace.lanes[0]);putchar(',');trace_lane(&trace.lanes[1]);
    }
    fputs("],\"rows\":[",stdout);
    row(&result.rows[0]);putchar(',');row(&result.rows[1]);
    fputs("]}\n",stdout);

    leo_differential_scout_destroy(scout);
    leo_native_glrt_destroy(detector);
    free(ranking);free(scores);free(energy);free(filters);
    free(control);free(exact);free(samples);
    return EXIT_SUCCESS;
}
