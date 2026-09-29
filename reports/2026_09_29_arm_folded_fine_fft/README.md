# Half-length modulo-folded fine FFT

This experiment starts from the preferred final-reuse fine2 checked/raw-condition implementation. For each selected fine-estimator frame, it retains every original weighted sample and accumulates sample `k` into FFT input `k` or `k-M`, where `M=rate/1000`. The resulting M-point DFT equals the even bins of the original `rate/500` transform, apart from FP32 accumulation order. The fine grid and parabolic interpolation step are therefore 1000 Hz.

All two estimator frames, coarse lanes, conditioned moments v3, cache behavior, and final FP64 GLRT remain unchanged. Host and sanitizer tests execute locally; ARM is cross-compiled only. The dedicated component test compares positive, zero, and negative wrapped bins with a direct DFT for all four sample rates and both full and partial inputs. This is an approximate coarser fine-CFO search and needs cohort recovery measurement before promotion.
