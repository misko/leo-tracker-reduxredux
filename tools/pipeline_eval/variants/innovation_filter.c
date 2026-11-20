#include <stddef.h>

/* A scalar innovations recurrence for each column of an irregular time series.
 * All strides are measured in doubles. C- and Fortran-ordered arrays can use
 * the same weights without transposing observations or allocating a matrix. */
void leo_filter_innovations(
    size_t times, size_t columns, const double *input,
    ptrdiff_t time_step, ptrdiff_t channel_step,
    double *output, ptrdiff_t out_time_step, ptrdiff_t out_channel_step,
    const double *decay, const double *inverse_sd, const double *band)
{
    if (!times || !columns)
        return;
    for (size_t j = 0; j < columns; ++j)
        output[(ptrdiff_t)j * out_channel_step] =
            input[(ptrdiff_t)j * channel_step] * inverse_sd[0];

    if (out_channel_step == 1 && columns > 1) {
        for (size_t i = 1; i < times; ++i) {
            const double *value = input + (ptrdiff_t)i * time_step;
            const double *last = value - time_step;
            double *result = output + (ptrdiff_t)i * out_time_step;
            const double *previous = result - out_time_step;
            for (size_t j = 0; j < columns; ++j) {
                ptrdiff_t k = (ptrdiff_t)j * channel_step;
                result[j] = (value[k] - decay[i - 1] * last[k]) * inverse_sd[i]
                          - band[i - 1] * previous[j];
            }
        }
    } else {
        for (size_t j = 0; j < columns; ++j) {
            const double *value = input + (ptrdiff_t)j * channel_step;
            double *result = output + (ptrdiff_t)j * out_channel_step;
            double last_value = *value, last_result = *result;
            for (size_t i = 1; i < times; ++i) {
                value += time_step;
                result += out_time_step;
                *result = (*value - decay[i - 1] * last_value) * inverse_sd[i]
                        - band[i - 1] * last_result;
                last_value = *value;
                last_result = *result;
            }
        }
    }
}
