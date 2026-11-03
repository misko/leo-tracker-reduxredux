#ifndef LEO_OPT_FOLD_DOUBLE_H
#define LEO_OPT_FOLD_DOUBLE_H
#include <stdint.h>
/* Private CI16 fold conversion. At most 16 products of two signed 16-bit
 * complex values bound each sum by 2^35. Split before converting so ARMv7
 * uses two native 32-bit VFP conversions instead of __floatdidf per cell.
 * GCC arithmetic signed shift and uint16_t's modulo conversion reconstruct
 * negative values too. Both components and their sum are exact in FP64.
 * This is not a general-purpose int64 conversion (precondition |x|<=2^36). */
static inline double opt_fold_double(int64_t x)
{
    return (double)(int32_t)(x >> 16)*65536.0+(double)(uint16_t)x;
}
#endif
