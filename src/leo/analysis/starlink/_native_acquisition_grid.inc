LEO_GRID_TARGET static void LEO_GRID_FUNCTION(FoldedAnchorGridKernel *kernel) {
    const npy_cdouble *restrict samples = kernel->samples;
    const npy_cdouble *restrict references = kernel->references;
    const double *restrict frequencies = kernel->frequencies;
    const npy_intp *restrict starts = kernel->starts;
    const npy_intp *restrict stops = kernel->stops;
    const npy_intp *restrict offsets = kernel->offsets;
    const double *restrict prefix = kernel->prefix;
    double *restrict scores = kernel->scores;
    double *restrict accumulated = kernel->accumulated;
    npy_int32 *restrict support = kernel->support;
    double *restrict correlation_real = kernel->correlation_real;
    double *restrict correlation_imag = kernel->correlation_imag;
    double *restrict rotated_real = kernel->rotated_real;
    double *restrict rotated_imag = kernel->rotated_imag;
    int invalid_geometry = 0;

    for (npy_intp symbol = 0; symbol < kernel->symbol_count && !invalid_geometry; ++symbol) {
        const npy_intp local_start = starts[symbol];
        const npy_intp reference_count = stops[symbol] - local_start;
        double reference_energy = 0.0;
        for (npy_intp index = 0; index < reference_count; ++index) {
            const npy_cdouble reference = references[local_start + index];
            const double reference_real = creal(reference);
            const double reference_imag = cimag(reference);
            reference_energy +=
                reference_real * reference_real + reference_imag * reference_imag;
            for (npy_intp frequency = 0; frequency < kernel->cfo_count; ++frequency) {
                const double angle =
                    6.283185307179586476925286766559 * frequencies[frequency] *
                    index / kernel->sample_rate_hz;
                const double cosine = cos(angle);
                const double sine = sin(angle);
                const npy_intp rotated_index = index * kernel->cfo_count + frequency;
                rotated_real[rotated_index] =
                    reference_real * cosine - reference_imag * sine;
                rotated_imag[rotated_index] =
                    reference_real * sine + reference_imag * cosine;
            }
        }
        const npy_intp valid_position_count = kernel->sample_count - reference_count + 1;
        for (npy_intp frame = 0; frame < kernel->offset_count; ++frame) {
            const npy_intp base = local_start + offsets[frame];
            if (base < 0) {
                invalid_geometry = 1;
                break;
            }
            if (base >= valid_position_count) {
                break;
            }
            npy_intp valid_epochs = valid_position_count - base;
            if (valid_epochs > kernel->epoch_count) {
                valid_epochs = kernel->epoch_count;
            }
            for (npy_intp epoch = 0; epoch < valid_epochs; ++epoch) {
                const npy_intp position = base + epoch;
                for (npy_intp frequency = 0; frequency < kernel->cfo_count; ++frequency) {
                    correlation_real[frequency] = 0.0;
                    correlation_imag[frequency] = 0.0;
                }
                for (npy_intp index = 0; index < reference_count; ++index) {
                    const npy_cdouble received = samples[position + index];
                    const double received_real = creal(received);
                    const double received_imag = cimag(received);
                    const npy_intp rotated_base = index * kernel->cfo_count;
                    #if defined(__GNUC__)
                    #pragma GCC ivdep
                    #endif
                    for (npy_intp frequency = 0; frequency < kernel->cfo_count; ++frequency) {
                        const double reference_real = rotated_real[rotated_base + frequency];
                        const double reference_imag = rotated_imag[rotated_base + frequency];
                        correlation_real[frequency] +=
                            received_real * reference_real +
                            received_imag * reference_imag;
                        correlation_imag[frequency] +=
                            received_imag * reference_real -
                            received_real * reference_imag;
                    }
                }
                double received_energy =
                    prefix[position + reference_count] - prefix[position];
                if (received_energy < 0.0) {
                    received_energy = 0.0;
                }
                const double denominator = sqrt(reference_energy * received_energy);
                if (denominator > 0.0) {
                    const npy_intp score_base = epoch * kernel->cfo_count;
                    if (kernel->fast_magnitude) {
                        for (npy_intp frequency = 0; frequency < kernel->cfo_count; ++frequency) {
                            const double real = correlation_real[frequency];
                            const double imag = correlation_imag[frequency];
                            accumulated[score_base + frequency] +=
                                sqrt(real * real + imag * imag) / denominator;
                        }
                    } else {
                        for (npy_intp frequency = 0; frequency < kernel->cfo_count; ++frequency) {
                            accumulated[score_base + frequency] +=
                                hypot(
                                    correlation_real[frequency],
                                    correlation_imag[frequency]) /
                                denominator;
                        }
                    }
                }
                support[epoch] += 1;
            }
        }
    }
    if (!invalid_geometry) {
        for (npy_intp frequency = 0; frequency < kernel->cfo_count; ++frequency) {
            for (int epoch = 0; epoch < kernel->epoch_count; ++epoch) {
                scores[frequency * kernel->epoch_count + epoch] = support[epoch] > 0
                    ? accumulated[epoch * kernel->cfo_count + frequency] /
                        support[epoch]
                    : 0.0;
            }
        }
    }
    kernel->invalid_geometry = invalid_geometry;
}
