/* Small private blocks eliminate independently, before the stock shared Schur factor. */
enum { NB_PRIVATE = 8, NB_PRIVATE_SQUARE = NB_PRIVATE * NB_PRIVATE };

static int inverse_private(int nd, const double *d, double *inverse, double *logdet,
                           double min_rcond, potrf_fn potrf, potri_fn potri, pocon_fn pocon) {
    double compact[NB_PRIVATE_SQUARE];
    double norm = 0.;
    for (int j = 0; j < nd; j++) {
        double column = 0.;
        for (int i = 0; i < nd; i++) {
            double value = d[j * NB_PRIVATE + i];
            compact[j * nd + i] = value;
            column += fabs(value);
        }
        if (column > norm) norm = column;
    }
    if (potrf(102, 'L', nd, compact, nd)) return NB_SPD;
    double rcond = 0.;
    if (pocon(102, 'L', nd, compact, nd, norm, &rcond) || !isfinite(rcond) || rcond < min_rcond)
        return NB_CONDITION;
    for (int j = 0; j < nd; j++) *logdet += 2. * log(compact[j * (nd + 1)]);
    if (potri(102, 'L', nd, compact, nd)) return NB_SPD;
    for (int j = 0; j < nd; j++) {
        for (int i = j; i < nd; i++) {
            double value = compact[j * nd + i];
            inverse[i * NB_PRIVATE + j] = inverse[j * NB_PRIVATE + i] = value;
        }
    }
    return NB_OK;
}
