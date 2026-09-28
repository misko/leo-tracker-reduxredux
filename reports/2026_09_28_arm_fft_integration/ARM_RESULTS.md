# ARM integration results

The ARM V4 integration unit passed every rate, full and partial randomized
complex inputs, zero inputs, the forced fallback, and the high-dynamic-range
fallback. The exact test output and source receipt are in `arm-unit-v4/` and
`builds/arm-v4/`.

The saved-IQ timing set contains 16 probe windows: four at each sample rate.
All 128 candidate objects are bit-exact against the preceding conditioned-CZT
ARM build. Unselected FFT proposal cells may differ. This is separate evidence from the host
704-dwell comparison; ARM did not run a 704-dwell FFT cohort.

| Rate | CZT mean CPU ms | FFT V4 mean CPU ms | Speedup |
| ---: | ---: | ---: | ---: |
| 2.5 MS/s | 1569.248450 | 1596.080843 | 0.9832x |
| 5 MS/s | 4398.393146 | 3768.729389 | 1.1671x |
| 7.5 MS/s | 8888.103936 | 6237.798188 | 1.4249x |
| 10 MS/s | 14112.964748 | 8614.717176 | 1.6382x |

ARM V5 restores the original direct coarse call site at 2.5 MS/s. Its matched
four-probe, three-repeat mean was 1589.513470 ms, versus 1559.839900 ms for the
conditioned-CZT build (0.9813317x), so the call-site change did not remove the regression.
The FFT binary is rejected at 2.5 MS/s. Exact V4 and V5 sources and receipts
are archived under `builds/arm-v4/` and `builds/arm-v5/`.

The separately developed screen-rotation V1 build remains the selected
2.5-MS/s result at 1542.867175 ms per probe and 33912.983283 ms per full
dual-RX dwell. It is not part of this FFT integration and cannot be combined
with the higher-rate FFT timings as one measured implementation.
