#ifndef POWCOMPAT_BARRIERS_H
#define POWCOMPAT_BARRIERS_H
#define math_opt_barrier(x) ({ __typeof(x) __x=(x); __asm__ ("" : "+m" (__x)); __x; })
#define math_force_eval(x) do { __typeof(x) __x=(x); __asm__ __volatile__ ("" : : "m" (__x)); } while (0)
#endif
