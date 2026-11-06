/* External prototype. Compile with -fno-fast-math -ffp-contract=off. */
#include <stddef.h>
#include <stdint.h>

int ordered_scatter(double *output, size_t output_size,
                    const intptr_t *indices, const intptr_t *groups,
                    const double *weights, size_t weight_size,
                    const double *values, size_t count) {
    /* Validate everything before mutating output. */
    for (size_t i = 0; i < count; ++i) {
        if (indices[i] < 0 || (size_t)indices[i] >= output_size ||
            groups[i] < 0 || (size_t)groups[i] >= weight_size)
            return 1;
    }
    for (size_t i = 0; i < count; ++i) {
        const double product = weights[groups[i]] * values[i];
        output[indices[i]] = output[indices[i]] + product;
    }
    return 0;
}
