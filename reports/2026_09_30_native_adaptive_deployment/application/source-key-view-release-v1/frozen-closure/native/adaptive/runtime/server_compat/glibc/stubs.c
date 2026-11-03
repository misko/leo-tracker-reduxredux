#include <math.h>
#include <stdint.h>
double __math_uflow(uint32_t s){ return s ? -0.0 : 0.0; }
double __math_oflow(uint32_t s){ return s ? -INFINITY : INFINITY; }
double __math_divzero(uint32_t s){ return s ? -INFINITY : INFINITY; }
double __math_invalid(double x){ return (x-x)/(x-x); }
