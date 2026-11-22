/* Isolated instrumentation for the two real timing passes. */
#include <stdint.h>
#include <time.h>

typedef struct {
    double trace, largest, leading_pair;
    uint64_t prefix_ns, covariance_ns;
    int skipped;
} CovarianceObservation;

static _Thread_local struct {
    CovarianceObservation rows[2];
    uint64_t prefix_start, covariance_start;
    double largest_limit, pair_limit;
    unsigned calls, gate;
    int skipped;
} covariance_probe;

void experimental_receiver_covariance_reset(unsigned gate, double largest_limit, double pair_limit) {
    covariance_probe.calls = 0;
    covariance_probe.gate = gate;
    covariance_probe.largest_limit = largest_limit;
    covariance_probe.pair_limit = pair_limit;
    covariance_probe.skipped = 0;
}

unsigned experimental_receiver_covariance_read(CovarianceObservation *rows, unsigned capacity) {
    if (rows && capacity >= covariance_probe.calls)
        memcpy(rows, covariance_probe.rows, covariance_probe.calls * sizeof(*rows));
    return covariance_probe.calls;
}

static uint64_t covariance_cpu_ns(void) {
    struct timespec instant;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &instant))
        return 0;
    return (uint64_t)instant.tv_sec * UINT64_C(1000000000) + (uint64_t)instant.tv_nsec;
}

static int covariance_record(double complex covariance[count][count]) {
    if (covariance_probe.calls >= 2)
        return 0;
    unsigned pass = covariance_probe.calls++;
    uint64_t end = covariance_cpu_ns();
    double total = 0., largest = 0., second = 0.;
    for (int i = 0; i < count; ++i) {
        double eigenvalue = creal(covariance[i][i]);
        total += eigenvalue;
        if (eigenvalue > largest) {
            second = largest;
            largest = eigenvalue;
        } else if (eigenvalue > second) {
            second = eigenvalue;
        }
    }
    double first_share = 0., pair_share = 0.;
    int valid = total > 0. && isfinite(total) && isfinite(largest) && isfinite(second);
    if (valid) {
        first_share = largest / total;
        pair_share = (largest + second) / total;
    }
    /* Gate bits 1 and 2 are primary and signed residual. Bit 4 is only
       used for calibration, which needs the covariance but no candidate. */
    int skip = valid && ((covariance_probe.gate & 4u) ||
        ((covariance_probe.gate & (1u << pass)) && first_share <= covariance_probe.largest_limit &&
         pair_share <= covariance_probe.pair_limit));
    covariance_probe.rows[pass] = (CovarianceObservation){
        total, first_share, pair_share,
        end - covariance_probe.prefix_start, end - covariance_probe.covariance_start, skip,
    };
    return covariance_probe.skipped = skip;
}
