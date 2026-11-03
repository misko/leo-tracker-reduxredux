#ifndef POWCOMPAT_MATH_CONFIG_H
#define POWCOMPAT_MATH_CONFIG_H
#include <math.h>
#include <stdint.h>

#define WANT_ROUNDING 1
#define WANT_ERRNO 0
#define TOINT_INTRINSICS 0
#define EXP_TABLE_BITS 7
#define EXP_POLY_ORDER 5
#define EXP2_POLY_ORDER 5
#define POW_LOG_TABLE_BITS 7
#define POW_LOG_POLY_ORDER 8
#define attribute_hidden
#ifndef __glibc_unlikely
#define __glibc_unlikely(x) __builtin_expect(!!(x), 0)
#endif

static inline uint64_t asuint64(double f) { union { double f; uint64_t i; } u={f}; return u.i; }
static inline double asdouble(uint64_t i) { union { uint64_t i; double f; } u={i}; return u.f; }
static inline int issignaling_inline(double x) {
  uint64_t ix=asuint64(x);
  return 2*(ix ^ UINT64_C(0x0008000000000000)) > 2*UINT64_C(0x7ff8000000000000);
}
static inline double check_oflow(double x) { return x; }
static inline double check_uflow(double x) { return x; }
double __math_uflow(uint32_t);
double __math_oflow(uint32_t);
double __math_divzero(uint32_t);
double __math_invalid(double);

extern const struct exp_data {
  double invln2N, negln2hiN, negln2loN, poly[4], shift;
  double exp2_shift, exp2_poly[EXP2_POLY_ORDER];
  double neglog10_2hiN, neglog10_2loN, exp10_poly[5], invlog10_2N;
  uint64_t tab[2*(1 << EXP_TABLE_BITS)];
} __exp_data;

extern const struct pow_log_data {
  double ln2hi, ln2lo, poly[POW_LOG_POLY_ORDER-1];
  struct { double invc, pad, logc, logctail; } tab[1 << POW_LOG_TABLE_BITS];
} __pow_log_data;
#endif
