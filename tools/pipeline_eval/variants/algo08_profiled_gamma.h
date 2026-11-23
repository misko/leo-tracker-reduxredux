/* Limited-memory minimization of the Gaussian-profiled Gamma objective. */
enum { GAMMA_MEMORY = 4, GAMMA_WARMUP = 3, GAMMA_LIMIT = 96 };
enum { GAMMA_EVALUATIONS, GAMMA_TRIALS, GAMMA_ACCEPTED, GAMMA_REJECTED,
       GAMMA_REPLAYS, GAMMA_COUNT };
static _Thread_local uint64_t gamma_counts[GAMMA_COUNT];

void nb_profiled_gamma_counts(uint64_t *out) {
    memcpy(out, gamma_counts, sizeof(gamma_counts));
}

typedef struct {
    int n, used, position, initialized, pending;
    double target;
    double *scale, *x, *gradient, *last_x, *last_gradient, *ordinary, *direction;
    double *steps, *changes;
    double curvature[GAMMA_MEMORY];
} GammaOptimizer;

static double gamma_dot(int n, const double *left, const double *right) {
    double value = 0.;
    for (int i = 0; i < n; ++i) value += left[i] * right[i];
    return value;
}

static void gamma_record(GammaOptimizer *opt) {
    const int n = opt->n, slot = opt->position;
    double *step = opt->steps + (size_t)slot*n;
    double *change = opt->changes + (size_t)slot*n;
    for (int i = 0; i < n; ++i) {
        step[i] = opt->x[i] - opt->last_x[i];
        change[i] = opt->gradient[i] - opt->last_gradient[i];
    }
    double curvature = gamma_dot(n, step, change);
    if (!(curvature > 1e-14)) {
        opt->used = 0;
        return;
    }
    opt->curvature[slot] = curvature;
    opt->position = (slot+1) % GAMMA_MEMORY;
    if (opt->used < GAMMA_MEMORY) ++opt->used;
}

static void gamma_direction(GammaOptimizer *opt) {
    const int n = opt->n;
    double alpha[GAMMA_MEMORY], initial = 1.;
    double *direction = opt->direction;
    memcpy(direction, opt->gradient, (size_t)n*sizeof(double));
    for (int j = 0; j < opt->used; ++j) {
        int slot = (opt->position + GAMMA_MEMORY - j - 1) % GAMMA_MEMORY;
        const double *step = opt->steps + (size_t)slot*n;
        const double *change = opt->changes + (size_t)slot*n;
        alpha[j] = gamma_dot(n, step, direction) / opt->curvature[slot];
        for (int i = 0; i < n; ++i) direction[i] -= alpha[j] * change[i];
        if (j == 0) initial = fmax(.25, fmin(16., opt->curvature[slot] / gamma_dot(n, change, change)));
    }
    for (int i = 0; i < n; ++i) direction[i] *= initial;
    for (int j = opt->used-1; j >= 0; --j) {
        int slot = (opt->position + GAMMA_MEMORY - j - 1) % GAMMA_MEMORY;
        const double *step = opt->steps + (size_t)slot*n;
        const double *change = opt->changes + (size_t)slot*n;
        double delta = alpha[j] - gamma_dot(n, change, direction) / opt->curvature[slot];
        for (int i = 0; i < n; ++i) direction[i] += step[i] * delta;
    }
}

/* A projected log-rate proposal is accepted only after a fresh exact posterior. */
static void gamma_next(GammaOptimizer *opt, int k, int t, double *rate, double *prate,
                       const double *next_rate, const double *next_prate, double beta,
                       double pb, double objective, double *change, int iteration) {
    if (opt->pending && !(objective <= opt->target)) {
        memcpy(rate, opt->ordinary, (size_t)k*sizeof(double));
        memcpy(prate, opt->ordinary+k, (size_t)t*sizeof(double));
        opt->pending = opt->initialized = opt->used = 0;
        *change = INFINITY;
        ++gamma_counts[GAMMA_REJECTED];
        return;
    }
    if (opt->pending) ++gamma_counts[GAMMA_ACCEPTED];
    opt->pending = 0;
    for (int j = 0; j < opt->n; ++j) {
        double current = j<k ? rate[j] : prate[j-k];
        double next = j<k ? next_rate[j] : next_prate[j-k];
        opt->x[j] = log(current) * opt->scale[j];
        opt->gradient[j] = (1. - next/current) * opt->scale[j];
        opt->ordinary[j] = next;
    }
    if (opt->initialized) gamma_record(opt);
    memcpy(opt->last_x, opt->x, (size_t)opt->n*sizeof(double));
    memcpy(opt->last_gradient, opt->gradient, (size_t)opt->n*sizeof(double));
    opt->initialized = 1;
    memcpy(rate, next_rate, (size_t)k*sizeof(double));
    memcpy(prate, next_prate, (size_t)t*sizeof(double));
    if (iteration < GAMMA_WARMUP || !opt->used || *change < 1e-5) return;
    gamma_direction(opt);
    double max_step = 0.;
    for (int j = 0; j < opt->n; ++j) max_step = fmax(max_step, fabs(opt->direction[j]/opt->scale[j]));
    double fraction = fmin(1., .75/max_step), slope = 0.;
    for (int j = 0; j < opt->n; ++j) {
        double floor = j<k ? beta : pb;
        opt->direction[j] = fmax(log(floor)*opt->scale[j], opt->x[j] - fraction*opt->direction[j]);
        slope += opt->gradient[j]*(opt->direction[j]-opt->x[j]);
    }
    if (!(slope < 0.) || !isfinite(slope)) return;
    for (int j = 0; j < opt->n; ++j) {
        double proposal = fmax(j<k ? beta : pb, exp(opt->direction[j]/opt->scale[j]));
        if (j<k) rate[j] = proposal; else prate[j-k] = proposal;
    }
    opt->pending = 1;
    opt->target = objective + 1e-4 * slope;
    *change = INFINITY;
    ++gamma_counts[GAMMA_TRIALS];
}
