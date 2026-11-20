/* Float32 differential timing scout. Reference spectra enter from the pinned Python scorer. */
#include <fftw3.h>
#include <math.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { times = 200000, receivers = 2, lag = 44, frame = 13333,
       pairs = times - lag, fold = 2 * frame - 1, fft = 32768, branches = 3 };

typedef struct {
    fftwf_complex *products;
    fftwf_complex *work;
    fftwf_complex *transforms;
    fftwf_plan forward, inverse;
} scout_context;

static int min(int a, int b) { return a < b ? a : b; }
static int max(int a, int b) { return a > b ? a : b; }

void leo_differential_scout_destroy(scout_context *s)
{
    if (!s) return;
    if (s->forward) fftwf_destroy_plan(s->forward);
    if (s->inverse) fftwf_destroy_plan(s->inverse);
    fftwf_free(s->products);
    fftwf_free(s->work);
    fftwf_free(s->transforms);
    free(s);
}

scout_context *leo_differential_scout_create(void)
{
    scout_context *s = calloc(1, sizeof(*s));
    if (!s) return NULL;
    s->products = fftwf_alloc_complex(pairs);
    s->work = fftwf_alloc_complex(fft);
    s->transforms = fftwf_alloc_complex(branches * fft);
    if (s->work) {
        s->forward = fftwf_plan_dft_1d(fft, s->work, s->work, FFTW_FORWARD, FFTW_ESTIMATE);
        s->inverse = fftwf_plan_dft_1d(fft, s->work, s->work, FFTW_BACKWARD, FFTW_ESTIMATE);
    }
    if (s->products && s->work && s->transforms && s->forward && s->inverse) return s;
    leo_differential_scout_destroy(s);
    return NULL;
}

static void center_products(fftwf_complex *out, const int16_t *data, int lane)
{
    double real_sum = 0., imag_sum = 0.;
    for (int i = 0; i < pairs; ++i) {
        const int16_t *a = data + 2 * (receivers * i + lane);
        const int16_t *b = a + 2 * receivers * lag;
        float ai = a[0], aq = a[1], bi = b[0], bq = b[1];
        out[i][0] = ai * bi + aq * bq;
        out[i][1] = ai * bq - aq * bi;
        real_sum += out[i][0];
        imag_sum += out[i][1];
    }
    double mean_real = real_sum / pairs, mean_imag = imag_sum / pairs;
    for (int i = 0; i < pairs; ++i) {
        out[i][0] -= mean_real;
        out[i][1] -= mean_imag;
    }
}

static void fold_lane(scout_context *s)
{
    /* round(m * 10000000 / 750) for m=-1,...,14; residue m mod 3. */
    static const int starts[] = {
        -13333, 0, 13333, 26667, 40000, 53333, 66667, 80000,
        93333, 106667, 120000, 133333, 146667, 160000, 173333, 186667
    };
    for (int r = 0; r < branches; ++r) {
        memset(s->work, 0, fft * sizeof(*s->work));
        for (int m = (r + 1) % branches; m < 16; m += branches) {
            int start = starts[m], end = min(fold, pairs - start);
            for (int i = max(-start, 0); i < end; ++i) {
                s->work[i][0] += s->products[start + i][0];
                s->work[i][1] += s->products[start + i][1];
            }
        }
        fftwf_execute(s->forward);
        memcpy(s->transforms + r * fft, s->work, fft * sizeof(*s->work));
    }
}

void leo_differential_scout(scout_context *s, const int16_t *data,
                           const fftwf_complex *filters, const double *energy, double *scores)
{
    for (int lane = 0; lane < receivers; ++lane) {
        center_products(s->products, data, lane);
        fold_lane(s);
        double *lane_scores = scores + lane * frame;
        for (int control = 0; control < 2; ++control) {
            const fftwf_complex *filter = filters + control * branches * fft;
            for (int i = 0; i < fft; ++i) {
                float real = 0.f, imag = 0.f;
                for (int r = 0; r < branches; ++r) {
                    int index = r * fft + i;
                    const float *x = s->transforms[index], *y = filter[index];
                    real += x[0] * y[0] - x[1] * y[1];
                    imag += x[0] * y[1] + x[1] * y[0];
                }
                s->work[i][0] = real;
                s->work[i][1] = imag;
            }
            fftwf_execute(s->inverse);
            for (int i = 0; i < frame; ++i) {
                float a = hypotf(s->work[i][0] / fft, s->work[i][1] / fft);
                double power = (a * a) / energy[control * frame + i];
                if (control) lane_scores[i] -= power;
                else lane_scores[i] = power;
            }
        }
    }
}
