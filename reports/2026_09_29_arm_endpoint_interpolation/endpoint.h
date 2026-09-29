#ifndef LEO_ENDPOINT_INTERPOLATION_H
#define LEO_ENDPOINT_INTERPOLATION_H

#include "full_search.h"

#define LEO_ENDPOINT_MAX 8
#define LEO_ENDPOINT_SEEDS 16

typedef struct { int left, right; double timing_delta, cost; } leo_endpoint_pair;
typedef struct {
    int pair_count, left_unmatched_count, right_unmatched_count;
    leo_endpoint_pair pairs[LEO_ENDPOINT_MAX];
    int left_unmatched[LEO_ENDPOINT_MAX], right_unmatched[LEO_ENDPOINT_MAX];
} leo_endpoint_association;

int leo_endpoint_associate(uint32_t rate, const leo_full_search_result *left,
    const leo_full_search_result *right, leo_endpoint_association *out);
double leo_endpoint_wrap(uint32_t rate, double epoch);
double leo_endpoint_interpolate_epoch(uint32_t rate, double left_epoch,
    double right_epoch, int window);
double leo_endpoint_project_constant(uint32_t rate, double endpoint_epoch,
    int window);
int leo_endpoint_execution_window(int position);
double leo_endpoint_acquisition_anchor(double tracking_cfo_hz);

#endif
