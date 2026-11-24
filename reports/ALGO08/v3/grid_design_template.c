#include <stddef.h>
#include <stdint.h>
#include <string.h>

void grid_design_template(size_t rows, size_t width,
                          const double *fixed, const ptrdiff_t *phase,
                          const ptrdiff_t *orbit, const double *q, const double *sigma,
                          const double *derivative, const double *modes, double *output) {
    memcpy(output, fixed, rows * width * sizeof(*output));
    for (size_t i = 0; i < rows; ++i, output += width) {
        output[phase[i]] = (q[i] * derivative[i]) * sigma[i];
        if (orbit[i] >= 0) {
            for (size_t k = 0; k < 3; ++k) {
                output[orbit[i] + k] = (q[i] * modes[3 * i + k]) * 1.0;
            }
        }
    }
}
