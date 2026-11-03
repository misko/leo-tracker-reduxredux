#pragma once

#ifdef __cplusplus
extern "C" {
#endif

/* Relinkable implementation detail for finite support deviations. This is not
 * a general-purpose pow API and is exported only as the module's narrow LGPL
 * shared-library boundary. */
double leo_server_pow3_fma(double value);

#ifdef __cplusplus
}
#endif
