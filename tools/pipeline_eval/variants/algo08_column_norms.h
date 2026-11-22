/* The j lanes are independent. Keep the dense terms first, followed by
 * private-row terms in exactly the original group and column order. */
static double shared_column_norms(const Layout *layout, const double *dense,
                                  const double *private_rows, double *scratch) {
    const int s = layout->s;
    for (int j = 0; j < s; ++j) {
        double sum = 0.;
        for (int h = 0; h < s; ++h)
            sum += fabs(dense[(size_t)j * s + h]);
        scratch[j] = sum;
    }
    for (int g = 0; g < layout->k; ++g) {
        for (int c = 0; c < layout->width[g]; ++c) {
            const double *row = private_rows + (size_t)(2 * g + c) * s;
            for (int j = 0; j < s; ++j)
                scratch[j] += fabs(row[j]);
        }
    }
    double norm = 0.;
    for (int j = 0; j < s; ++j)
        if (scratch[j] > norm) norm = scratch[j];
    return norm;
}
