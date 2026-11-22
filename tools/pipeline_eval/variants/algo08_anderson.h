/* Degree-three Anderson mixing with a measured ordinary-successor safeguard. */
enum { AA_DEPTH = 3, AA_HISTORY = AA_DEPTH + 1, AA_REPLAY = 6 };
enum { AA_TRIALS, AA_ACCEPTED, AA_REJECTED, AA_EVALUATED, AA_COUNTS };
static _Thread_local int aa_counts[AA_COUNTS];

void nb_anderson_counts(int *out) {
    memcpy(out, aa_counts, sizeof(aa_counts));
}

typedef struct {
    int k, t, used, stage;
    double reference;
    double *images, *residuals, *proposal, *ordinary;
} Anderson;

static int combination(const Anderson *a, double *alpha) {
    int n = a->k + a->t;
    const double *last = a->residuals + (size_t)AA_DEPTH * n;
    double normal[AA_DEPTH][AA_DEPTH] = {{0.}}, targets[AA_DEPTH] = {0.};
    for (int j = 0; j < n; j++) {
        double delta[AA_DEPTH];
        for (int i = 0; i < AA_DEPTH; i++) delta[i] = a->residuals[(size_t)i*n+j] - last[j];
        for (int i = 0; i < AA_DEPTH; i++) {
            targets[i] -= delta[i] * last[j];
            for (int h = 0; h <= i; h++) normal[i][h] += delta[i] * delta[h];
        }
    }
    double scale = 0.;
    for (int i = 0; i < AA_DEPTH; i++) scale = fmax(scale, normal[i][i]);
    if (!(scale > 0.) || !isfinite(scale)) return 0;
    for (int i = 0; i < AA_DEPTH; i++) {
        for (int j = 0; j <= i; j++) {
            double value = normal[i][j];
            for (int h = 0; h < j; h++) value -= normal[i][h] * normal[j][h];
            if (i == j && !(value > 1e-10 * scale)) return 0;
            normal[i][j] = i == j ? sqrt(value) : value / normal[j][j];
        }
        for (int j = 0; j < i; j++) targets[i] -= normal[i][j] * targets[j];
        targets[i] /= normal[i][i];
    }
    alpha[AA_DEPTH] = 1.;
    for (int i = AA_DEPTH - 1; i >= 0; i--) {
        for (int j = i + 1; j < AA_DEPTH; j++) targets[i] -= normal[j][i] * alpha[j];
        alpha[i] = targets[i] / normal[i][i];
        alpha[AA_DEPTH] -= alpha[i];
    }
    double absolute_sum = 0.;
    for (int i = 0; i < AA_HISTORY; i++) absolute_sum += fabs(alpha[i]);
    return absolute_sum <= 8.;
}

static void sequence(Anderson *a, double *rate, double *prate, const double *next_rate,
                     const double *next_prate, double beta0, double pb0, double *change,
                     int more_updates) {
    int n = a->k + a->t;
    if (a->stage == 2) {
        a->stage = a->used = 0;
        if (*change <= 0.8 * a->reference) {
            aa_counts[AA_ACCEPTED]++;
        } else {
            aa_counts[AA_REJECTED]++;
            memcpy(rate, a->ordinary, a->k * sizeof(double));
            memcpy(prate, a->ordinary + a->k, a->t * sizeof(double));
            *change = INFINITY;
            return;
        }
    } else if (a->stage == 1) {
        a->stage = a->used = 0;
        if (*change >= 1e-5 && more_updates >= 1) {
            memcpy(a->ordinary, next_rate, a->k * sizeof(double));
            memcpy(a->ordinary + a->k, next_prate, a->t * sizeof(double));
            memcpy(rate, a->proposal, a->k * sizeof(double));
            memcpy(prate, a->proposal + a->k, a->t * sizeof(double));
            a->reference = *change;
            a->stage = 2;
            aa_counts[AA_TRIALS]++;
            *change = INFINITY;
            return;
        }
    } else if (*change >= 1e-5 && more_updates >= 2) {
        if (a->used == AA_HISTORY) {
            memmove(a->images, a->images + n, (size_t)AA_DEPTH*n*sizeof(double));
            memmove(a->residuals, a->residuals + n, (size_t)AA_DEPTH*n*sizeof(double));
            a->used--;
        }
        size_t offset = (size_t)a->used * n;
        for (int j = 0; j < n; j++) {
            double old = j < a->k ? rate[j] : prate[j-a->k];
            double next = j < a->k ? next_rate[j] : next_prate[j-a->k];
            a->images[offset+j] = log(next);
            a->residuals[offset+j] = log(next / old);
        }
        a->used++;
        double alpha[AA_HISTORY];
        if (a->used == AA_HISTORY && combination(a, alpha)) {
            a->stage = 1;
            for (int j = 0; j < n; j++) {
                double last = a->images[offset+j], candidate = last;
                for (int i = 0; i < AA_DEPTH; i++)
                    candidate += alpha[i] * (a->images[(size_t)i*n+j] - last);
                a->proposal[j] = exp(candidate);
                double minimum = j < a->k ? beta0 : pb0;
                if (fabs(candidate-last) > 4. * *change || !isfinite(a->proposal[j]) ||
                    a->proposal[j] < minimum) {
                    a->stage = 0;
                    break;
                }
            }
        }
    }
    memcpy(rate, next_rate, a->k * sizeof(double));
    memcpy(prate, next_prate, a->t * sizeof(double));
}
