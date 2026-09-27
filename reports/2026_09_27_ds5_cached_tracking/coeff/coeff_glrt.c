#define _POSIX_C_SOURCE 200809L
#include "known_state_v2.c"
#include "coeff_glrt.h"

#define COEFF_MAX_TABLES 16
#define COEFF_MAX_SYMBOL_SPAN 48

typedef struct {
    int used, first_symbol, source_start;
    uint32_t span[LEO_COEFF_SYMBOLS];
    int base[LEO_COEFF_SYMBOLS];
    double complex values[2][LEO_COEFF_SYMBOLS][COEFF_MAX_SYMBOL_SPAN];
} coeff_table;

struct leo_coeff_workspace {
    leo_presence_workspace *presence;
    coeff_table tables[COEFF_MAX_TABLES];
    uint32_t table_count;
};

typedef struct {
    double complex correlations[16][2][LEO_COEFF_SYMBOLS];
    double ceilings[2], scores[2], residual_hz;
    uint32_t peak_bin, frame_count;
} glrt_diagnostic;

static int actual_pattern_matches(leo_presence_workspace *w, int a, int b,
    int first_symbol, double offset)
{
    for (int symbol=first_symbol; symbol<first_symbol+LEO_COEFF_SYMBOLS; ++symbol) {
        int begin=symbol_start(w,symbol), end=symbol_start(w,symbol+1);
        for (int k=begin; k<end; ++k) {
            double pa=a+k+offset, pb=b+k+offset;
            int ba=(int)floor(pa)-a, bb=(int)floor(pb)-b;
            if (ba!=bb || pa-floor(pa)!=pb-floor(pb)) return 0;
        }
    }
    return 1;
}

static int build_table(leo_coeff_workspace *owner, coeff_table *table,
    int start, int first_symbol, double offset, const double complex *rotations)
{
    leo_presence_workspace *w=owner->presence;
    memset(table,0,sizeof(*table));
    table->used=1; table->first_symbol=first_symbol; table->source_start=start;
    double previous_fraction=NAN, normalized_weights[16]={0};
    for (int symbol=first_symbol; symbol<first_symbol+LEO_COEFF_SYMBOLS; ++symbol) {
        int row=symbol-first_symbol;
        int begin=symbol_start(w,symbol), end=symbol_start(w,symbol+1);
        int base=(int)floor(start+begin+offset)-start-7;
        int limit=(int)floor(start+end-1+offset)-start+8;
        int span=limit-base+1;
        if (span<=0 || span>COEFF_MAX_SYMBOL_SPAN) return -1;
        table->base[row]=base;
        table->span[row]=(uint32_t)span;
        for (int k=begin; k<end; ++k) {
            double position=start+k+offset;
            int sample_base=(int)floor(position);
            double fraction=position-sample_base;
            if (fraction!=previous_fraction) {
                double normalizer=0, weights[16];
                for (int tap=-7; tap<=8; ++tap) {
                    double distance=position-(sample_base+tap);
                    weights[tap+7]=sinc(distance)*sinc(distance/8);
                    normalizer+=weights[tap+7];
                }
                if (!isfinite(normalizer) || normalizer==0) return -1;
                for (int tap=0; tap<16; ++tap)
                    normalized_weights[tap]=weights[tap]/normalizer;
                previous_fraction=fraction;
            }
            for (int which=0; which<2; ++which) {
                const double complex *reference=which ? w->control : w->exact;
                double complex pilot=conj(reference[k])*rotations[k];
                for (int tap=-7; tap<=8; ++tap) {
                    int relative=sample_base+tap-start-base;
                    table->values[which][row][relative]+=
                        pilot*normalized_weights[tap+7];
                }
            }
        }
    }
    return 0;
}

static coeff_table *find_or_build(leo_coeff_workspace *owner, int start,
    int first_symbol, double offset, const double complex *rotations,
    leo_coeff_result *result)
{
    for (uint32_t k=0; k<owner->table_count; ++k) {
        coeff_table *table=&owner->tables[k];
        if (table->first_symbol==first_symbol && actual_pattern_matches(
            owner->presence,table->source_start,start,first_symbol,offset)) {
            ++result->coefficient_table_hits;
            return table;
        }
    }
    if (owner->table_count>=COEFF_MAX_TABLES) return NULL;
    coeff_table *table=&owner->tables[owner->table_count++];
    double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    if (build_table(owner,table,start,first_symbol,offset,rotations)) return NULL;
    result->coefficient_build_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
    ++result->coefficient_tables_built;
    return table;
}

static void finish_diagnostic(leo_presence_workspace *w, glrt_diagnostic *out)
{
    double spectra[2][128]={{0}};
    for (uint32_t frame=0; frame<out->frame_count; ++frame) {
        for (int which=0; which<2; ++which) {
            memset(w->input,0,128*sizeof(*w->input));
            double ceiling=0;
            for (int k=0; k<LEO_COEFF_SYMBOLS; ++k) {
                w->input[k]=out->correlations[frame][which][k];
                ceiling+=cabs(w->input[k]);
            }
            out->ceilings[which]+=ceiling*ceiling;
            leo_fft_forward(&w->short_fft,w->input);
            for (int k=0; k<128; ++k)
                spectra[which][k]+=power(w->short_fft.output[k]);
        }
    }
    for (int which=0; which<2; ++which) {
        for (int k=0; k<128; ++k) w->input[k]=spectra[which][k];
        leo_fft_forward(&w->short_fft,w->input);
        memset(w->input,0,512*sizeof(*w->input));
        for (int k=0; k<64; ++k) w->input[k]=conj(w->short_fft.output[k])/128;
        for (int k=1; k<64; ++k) w->input[512-k]=conj(w->short_fft.output[128-k])/128;
        leo_fft_forward(&w->glrt_fft,w->input);
        int best=0;
        for (int k=1; k<512; ++k)
            if (creal(w->glrt_fft.output[k])>creal(w->glrt_fft.output[best])) best=k;
        out->scores[which]=out->ceilings[which]>0 ?
            creal(w->glrt_fft.output[best])/out->ceilings[which] : 0;
        if (which==0 && out->ceilings[which]>0) {
            out->peak_bin=(uint32_t)best;
            out->residual_hz=(best<256 ? best : best-512)/(512*SYMBOL_S);
        }
    }
}

static int original_correlations(leo_presence_workspace *w, size_t count,
    int epoch, double cfo, double offset, glrt_diagnostic *out)
{
    if (epoch<0 || epoch>=(int)w->n || !isfinite(cfo) || fabs(cfo)>400000 ||
        !isfinite(offset) || fabs(offset)>2) return -1;
    int integer=fabs(offset-nearbyint(offset))<=1e-12;
    double complex *rotations=w->glrt_rotations;
    w->rotation_cfo=cfo; w->rotation_offset=offset; w->have_rotations=0;
    for (int region=0; region<=1; ++region) {
        for (int k=symbol_start(w,2+150*region); k<symbol_start(w,66+150*region); ++k)
            rotations[k]=rotate(-TAU*cfo*(k+offset)/w->rate);
        w->have_rotations|=1<<region;
    }
    double previous_fraction=NAN, weights[16], normalizer=0;
    int frames=0;
    for (int frame=0; frame<16; ++frame) {
        int start=frame_start(w,epoch,frame);
        int first_symbol=(frame&1) ? 152 : 2;
        int first=symbol_start(w,first_symbol), stop=symbol_start(w,first_symbol+64);
        if (first_symbol!=2 && start+stop-1+offset >= (int)count-(integer ? 0 : 8)) {
            first_symbol=2; first=symbol_start(w,2); stop=symbol_start(w,66);
        }
        if (start+stop-1+offset >= (double)count-(integer ? 0 : 8)) break;
        if (start+first+offset < (integer ? 0 : 7)) break;
        for (int symbol=first_symbol; symbol<first_symbol+64; ++symbol) {
            int begin=symbol_start(w,symbol), end=symbol_start(w,symbol+1);
            double complex corr[2]={0};
            for (int k=begin; k<end; ++k) {
                double position=start+k+offset;
                double complex received=0;
                if (integer) received=w->samples[(int)nearbyint(position)];
                else {
                    int base=(int)floor(position);
                    double fraction=position-base;
                    if (fraction!=previous_fraction) {
                        normalizer=0;
                        for (int tap=-7; tap<=8; ++tap) {
                            double distance=position-(base+tap);
                            weights[tap+7]=sinc(distance)*sinc(distance/8);
                            normalizer+=weights[tap+7];
                        }
                        previous_fraction=fraction;
                    }
                    for (int tap=-7; tap<=8; ++tap)
                        received+=weights[tap+7]*w->samples[base+tap];
                    received/=normalizer;
                }
                double complex corrected=received*rotations[k];
                corr[0]+=conj(w->exact[k])*corrected;
                corr[1]+=conj(w->control[k])*corrected;
            }
            out->correlations[frames][0][symbol-first_symbol]=corr[0];
            out->correlations[frames][1][symbol-first_symbol]=corr[1];
        }
        ++frames;
    }
    if (!frames) return -1;
    out->frame_count=(uint32_t)frames;
    finish_diagnostic(w,out);
    return frames;
}

static int coefficient_correlations(leo_coeff_workspace *owner, size_t count,
    int epoch, double cfo, double offset, glrt_diagnostic *out,
    leo_coeff_result *result)
{
    leo_presence_workspace *w=owner->presence;
    int integer=fabs(offset-nearbyint(offset))<=1e-12;
    if (integer) return original_correlations(w,count,epoch,cfo,offset,out);
    double complex *rotations=w->glrt_rotations;
    w->rotation_cfo=cfo; w->rotation_offset=offset; w->have_rotations=0;
    for (int region=0; region<=1; ++region) {
        for (int k=symbol_start(w,2+150*region); k<symbol_start(w,66+150*region); ++k)
            rotations[k]=rotate(-TAU*cfo*(k+offset)/w->rate);
        w->have_rotations|=1<<region;
    }
    owner->table_count=0;
    int frames=0;
    for (int frame=0; frame<16; ++frame) {
        int start=frame_start(w,epoch,frame);
        int first_symbol=(frame&1) ? 152 : 2;
        int first=symbol_start(w,first_symbol), stop=symbol_start(w,first_symbol+64);
        if (first_symbol!=2 && start+stop-1+offset >= (int)count-8) {
            first_symbol=2; first=symbol_start(w,2); stop=symbol_start(w,66);
        }
        if (start+stop-1+offset >= (double)count-8) break;
        if (start+first+offset < 7) break;
        coeff_table *table=find_or_build(owner,start,first_symbol,offset,rotations,result);
        if (!table) return -1;
        double started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
        for (int which=0; which<2; ++which) {
            for (int row=0; row<64; ++row) {
                double complex value=0;
                int base=start+table->base[row];
                for (uint32_t j=0; j<table->span[row]; ++j)
                    value+=table->values[which][row][j]*w->samples[base+(int)j];
                out->correlations[frames][which][row]=value;
            }
        }
        result->coefficient_dot_cpu_ms+=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-started;
        ++frames;
    }
    if (!frames) return -1;
    out->frame_count=(uint32_t)frames;
    finish_diagnostic(w,out);
    return frames;
}

leo_coeff_workspace *leo_coeff_create(uint32_t rate,
    const leo_presence_complex *exact, const leo_presence_complex *control,
    size_t count)
{
    leo_coeff_workspace *w=calloc(1,sizeof(*w));
    if (!w) return NULL;
    w->presence=leo_presence_create(rate,exact,control,count);
    if (!w->presence) { free(w); return NULL; }
    return w;
}

void leo_coeff_destroy(leo_coeff_workspace *w)
{
    if (!w) return;
    leo_presence_destroy(w->presence);
    free(w);
}

int leo_coeff_measure_ci16(leo_coeff_workspace *owner, const int16_t *iq,
    size_t count, uint32_t stride, double predicted_epoch, double predicted_cfo,
    leo_coeff_result *out)
{
    if (!owner || !owner->presence || !iq || !out || count!=owner->presence->max_samples ||
        stride<2 || stride>16 || !isfinite(predicted_epoch) ||
        !isfinite(predicted_cfo) || fabs(predicted_cfo)>400000 ||
        fegetround()!=FE_TONEAREST) return -1;
    leo_coeff_result result={0};
    result.score.schema_version=1;
    result.score.predicted_epoch_samples=predicted_epoch;
    result.score.predicted_cfo_hz=predicted_cfo;
    result.score.scored_cfo_hz=predicted_cfo;
    result.score.valid_bounds=1;
    result.score.sample_stride_i16=stride;
    result.score.frame_limit=16;
    double cpu=clock_ms(CLOCK_PROCESS_CPUTIME_ID), wall=clock_ms(CLOCK_MONOTONIC);
    int epoch=0; double fractional=0;
    normalize_phase(owner->presence,predicted_epoch,&epoch,&fractional);
    double conversion_started=clock_ms(CLOCK_PROCESS_CPUTIME_ID);
    result.score.converted_samples=convert_glrt_support(
        owner->presence,iq,count,stride,epoch,fractional,16);
    result.score.conversion_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-conversion_started;
    glrt_diagnostic baseline={0}, coefficient={0};
    int coefficient_frames=coefficient_correlations(
        owner,count,epoch,predicted_cfo,fractional,&coefficient,&result);
    double candidate_cpu_ms=clock_ms(CLOCK_PROCESS_CPUTIME_ID)-cpu;
    double candidate_wall_ms=clock_ms(CLOCK_MONOTONIC)-wall;
    /* Oracle diagnostics run after candidate timing and are never hidden by a
     * warm cache. Coefficient tables are cleared inside every invocation. */
    int baseline_frames=original_correlations(
        owner->presence,count,epoch,predicted_cfo,fractional,&baseline);
    if (baseline_frames<=0 || coefficient_frames!=baseline_frames) return -1;
    result.score.epoch=epoch;
    result.score.fractional_offset_samples=fractional;
    result.score.scored_fractional=1;
    result.score.available_support_frames=(uint32_t)baseline_frames;
    result.score.support_frames=(uint32_t)baseline_frames;
    result.score.glrt_evaluations=1;
    result.score.exact_score=coefficient.scores[0];
    result.score.control_score=coefficient.scores[1];
    result.score.margin=coefficient.scores[0]-coefficient.scores[1];
    result.score.cfo_innovation_hz=coefficient.residual_hz;
    result.score.tracking_cfo_hz=predicted_cfo+coefficient.residual_hz;
    if (fabs(coefficient.residual_hz)>KNOWN_CFO_TRUST_HZ ||
        fabs(result.score.tracking_cfo_hz)>400000)
        result.score.status|=LEO_KNOWN_STATE_CFO_REACQUIRE;
    result.baseline_exact_score=baseline.scores[0];
    result.baseline_control_score=baseline.scores[1];
    result.baseline_cfo_residual_hz=baseline.residual_hz;
    result.baseline_peak_bin=baseline.peak_bin;
    result.coefficient_peak_bin=coefficient.peak_bin;
    double baseline_correlation_max=0;
    for (int which=0; which<2; ++which) {
        result.ceiling_max_abs_error=fmax(result.ceiling_max_abs_error,
            fabs(coefficient.ceilings[which]-baseline.ceilings[which]));
        result.ceiling_max_relative_error=fmax(result.ceiling_max_relative_error,
            fabs(coefficient.ceilings[which]-baseline.ceilings[which]) /
            fmax(fabs(baseline.ceilings[which]),DBL_MIN));
        for (int frame=0; frame<baseline_frames; ++frame) for (int k=0; k<64; ++k) {
            baseline_correlation_max=fmax(baseline_correlation_max,
                cabs(baseline.correlations[frame][which][k]));
            result.correlation_max_abs_error=fmax(result.correlation_max_abs_error,
                cabs(coefficient.correlations[frame][which][k]-
                    baseline.correlations[frame][which][k]));
        }
    }
    result.correlation_max_relative_error=result.correlation_max_abs_error /
        fmax(baseline_correlation_max,DBL_MIN);
    result.score.total_cpu_ms=candidate_cpu_ms;
    result.score.kernel_cpu_ms=result.score.total_cpu_ms-result.score.conversion_cpu_ms;
    result.score.total_wall_ms=candidate_wall_ms;
    *out=result;
    return 0;
}
