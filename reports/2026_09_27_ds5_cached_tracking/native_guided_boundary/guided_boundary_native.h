#ifndef LEO_RESEARCH_GUIDED_BOUNDARY_NATIVE_H
#define LEO_RESEARCH_GUIDED_BOUNDARY_NATIVE_H

#include "../tg11/tg11_native.h"

/* Scientific ABI is the frozen TG11-v1 ABI. This diagnostic export lets a
 * loader attest the exact numerical guard in the binary it opened. */
double leo_tg11_guided_support_guard_hz(void);

#endif
