#include "pow3.h"

double leo_server_pow_core(double, double);

__attribute__((visibility("default")))
double leo_server_pow3_fma(double value) {
    return leo_server_pow_core(value, 3.0);
}
