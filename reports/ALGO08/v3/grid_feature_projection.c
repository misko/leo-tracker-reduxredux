#include <math.h>
#include <stddef.h>
#include <string.h>

static const double carrier = -11.5e9;
static const double c_km_s = 299792.458;

/* The contiguous three-element NumPy einsum reduces the two lanes
 * before adding the right lane to the left one plus the tail. */
static double dot(const double *a, const double *b) {
    return (a[0] * b[0] + a[2] * b[2]) + a[1] * b[1];
}

static double relative(const double *p, const double *observer, double *line) {
    for (size_t i = 0; i < 3; ++i) {
        line[i] = p[i] - observer[i];
    }
    return sqrt((line[0] * line[0] + line[1] * line[1]) + line[2] * line[2]);
}

static double shifted(const double *p, const double *v, const double *observer) {
    double line[3];
    const double range = relative(p, observer, line);
    return range > 0.0 && isfinite(range)
        ? (carrier * (dot(line, v) / range)) / c_km_s
        : NAN;
}

int project_grid_phase(size_t rows, const double *observer, const double *p, const double *v,
                       const double *pp, const double *vp, const double *pm, const double *vm,
                       const double *dp, const double *dv, double *line, double *frequency,
                       double *difference, double *modes) {
    for (size_t i = 0; i < rows; ++i) {
        const size_t j = 3 * i;
        const double range = relative(p + j, observer, line + j);
        if (!(range > 0.0) || !isfinite(range)) {
            return 0;
        }
        frequency[i] = (carrier * (dot(line + j, v + j) / range)) / c_km_s;
        const double plus = shifted(pp + j, vp + j, observer);
        const double minus = shifted(pm + j, vm + j, observer);
        difference[i] = (plus - minus) / 0.02;

        double direction[3], gradient[3];
        for (size_t k = 0; k < 3; ++k) {
            direction[k] = line[j + k] / range;
        }
        const double rate = ((direction[0] * v[j] + direction[1] * v[j + 1])
                            + direction[2] * v[j + 2]) + 0.0;
        for (size_t k = 0; k < 3; ++k) {
            gradient[k] = (v[j + k] - rate * direction[k]) / range;
        }
        for (size_t k = 0; k < 3; ++k) {
            const size_t offset = 3 * (j + k);
            modes[j + k] = (carrier / c_km_s)
                * (dot(gradient, dp + offset) + dot(direction, dv + offset));
            if (!isfinite(modes[j + k])) {
                return 0;
            }
        }
        if (!isfinite(frequency[i]) || !isfinite(difference[i])) {
            return 0;
        }
    }
    return 1;
}

void select_grid_design(size_t rows, size_t width, const double *input, const double *scale,
                        const unsigned char *keep, double *output) {
    size_t prefix = 0;
    while (prefix < width && scale[prefix] == 1.0) {
        ++prefix;
    }
    for (size_t i = 0; i < rows; ++i, input += width) {
        if (!keep[i]) {
            continue;
        }
        memcpy(output, input, prefix * sizeof(*output));
        for (size_t j = prefix; j < width; ++j) {
            output[j] = input[j] * scale[j];
        }
        output += width;
    }
}
