/* A folded input FFT serves every cyclic correlation in the steering span. */
#include <fftw3.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    int size, rows, batch;
    fftwf_complex *input, *inverse;
    fftwf_plan forward, backward;
} SharedAmbiguity;

void shared_ambiguity_free(SharedAmbiguity *bank) {
    if (!bank) return;
    if (bank->backward) fftwf_destroy_plan(bank->backward);
    if (bank->forward) fftwf_destroy_plan(bank->forward);
    fftwf_free(bank->inverse);
    fftwf_free(bank->input);
    free(bank);
}

SharedAmbiguity *shared_ambiguity_create(int size, int rows, int batch) {
    if (size < 1 || size > 4800 || rows < 1 || rows > 704)
        return NULL;
    SharedAmbiguity *bank = calloc(1, sizeof(*bank));
    if (!bank) return NULL;
    bank->size = size;
    bank->rows = rows;
    bank->batch = batch;
    bank->input = fftwf_alloc_complex(size);
    bank->inverse = fftwf_alloc_complex((size_t)size * (batch ? rows : 1));
    if (!bank->input || !bank->inverse) {
        shared_ambiguity_free(bank);
        return NULL;
    }
    bank->forward = fftwf_plan_dft_1d(size, bank->input, bank->input, FFTW_FORWARD, FFTW_ESTIMATE);
    if (batch) {
        bank->backward = fftwf_plan_many_dft(1, &size, rows, bank->inverse, NULL, 1, size,
                                             bank->inverse, NULL, 1, size, FFTW_BACKWARD, FFTW_ESTIMATE);
    } else {
        bank->backward = fftwf_plan_dft_1d(size, bank->inverse, bank->inverse, FFTW_BACKWARD, FFTW_ESTIMATE);
    }
    if (!bank->forward || !bank->backward) {
        shared_ambiguity_free(bank);
        return NULL;
    }
    return bank;
}

static void apply_filter(int size, const fftwf_complex *input, const fftwf_complex *filter,
                         fftwf_complex *output) {
    for (int k = 0; k < size; ++k) {
        const float ar = input[k][0], ai = input[k][1], br = filter[k][0], bi = filter[k][1];
        output[k][0] = ar * br + ai * bi;
        output[k][1] = ai * br - ar * bi;
    }
}

/* Output, if requested, is an unnormalized cyclic correlation per basis row. */
int shared_ambiguity_run(SharedAmbiguity *bank, const fftwf_complex *row,
                         const fftwf_complex *spectra, fftwf_complex *output) {
    if (!bank || !row || !spectra)
        return -1;
    const int size = bank->size;
    const size_t bytes = (size_t)size * sizeof(fftwf_complex);
    memcpy(bank->input, row, bytes);
    fftwf_execute(bank->forward);
    for (int i = 0; i < bank->rows; ++i) {
        const size_t offset = (size_t)i * size;
        fftwf_complex *inverse = bank->inverse + (bank->batch ? offset : 0);
        apply_filter(size, bank->input, spectra + offset, inverse);
        if (!bank->batch) {
            fftwf_execute(bank->backward);
            if (output) memcpy(output + offset, inverse, bytes);
        }
    }
    if (bank->batch) {
        fftwf_execute(bank->backward);
        if (output) memcpy(output, bank->inverse, bank->rows * bytes);
    }
    return 0;
}
