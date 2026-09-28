# Independent coarse FFT edge fixtures

`test_fft_edges.c` includes the private `full_search.c` translation unit so it
can inspect the direct FP32 coarse grid left by `leo_fft_coarse_qualify`.
It is deliberately a separate host-only test binary and is not part of the
qualified probe/cohort build.

The fixture creates centered complex template and control data, a 0.02-amplitude
centered complex background, and a 3x exact-template anchor at the requested
epoch across every valid rounded frame offset.  It checks both that the final
direct grid's maximum is the injected `(epoch, CFO bin 5)` and that the
proposal qualification retained inventory equals direct with no fallback.

Executed command:

```sh
gcc -DLEO_PRESENCE_FFTW=1 -std=c11 -O3 -Wall -Wextra -Werror -fno-fast-math \
  -DLEO_PRESENCE_COARSE_FP32 -DLEO_FULL_CONDITIONED_SCREEN \
  -I /var/tmp/leo-host-conditioned-czt-v2/src/native_presence \
  -I /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_28_arm_fft_integration \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_28_arm_fft_integration/test_fft_edges.c \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_28_arm_fft_integration/conditioned_czt.c \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_09_28_arm_fft_integration/fft_full.c \
  -lfftw3 -lfftw3f -lm -o /var/tmp/leo-fft-edge-test && /var/tmp/leo-fft-edge-test
```

Output:

```
rate=5000000 epoch=0 direct_epoch=0 direct_bin=5 equal=1 repaired=7 fallback=0 error=5.08626302e-07
rate=5000000 epoch=6666 direct_epoch=6666 direct_bin=5 equal=1 repaired=7 fallback=0 error=4.66240777e-07
rate=7500000 epoch=0 direct_epoch=0 direct_bin=5 equal=1 repaired=5 fallback=0 error=4.17585204e-07
rate=7500000 epoch=9999 direct_epoch=9999 direct_bin=5 equal=1 repaired=5 fallback=0 error=5.08626302e-07
rate=10000000 epoch=0 direct_epoch=0 direct_bin=5 equal=1 repaired=5 fallback=0 error=5.61608209e-07
rate=10000000 epoch=13332 direct_epoch=13332 direct_bin=5 equal=1 repaired=8 fallback=0 error=4.31424096e-07
rate=5000000 epoch=106 direct_epoch=106 direct_bin=5 equal=1 repaired=9 fallback=0 error=5.7220459e-07
rate=5000000 epoch=107 direct_epoch=107 direct_bin=5 equal=1 repaired=12 fallback=0 error=5.29819065e-07
fft coarse edge fixtures passed
```

The observed unrepaired maximum absolute grid differences ranged from
`4.17585204e-7` to `5.7220459e-7`.  These are host edge-fixture results, not
an ARM or end-to-end performance result.
