# Cached FP32 rotated-template final-GLRT dot

This experiment starts from the standalone NEON conditioned-moments v2 fine2 scorer and adds direct CI16 access. For each distinct executed GLRT CFO, it generates rotated exact/control templates directly into workspace-owned interleaved FP32 arrays only for the one or two 64-symbol regions used by final scoring. Those arrays are reused across all 16 frames. This removes the rejected earlier FP32 scorer's per-call allocation, full-length FP64-to-FP32 copy, and unused-template conversion.

The ARM dot kernel deinterleaves stride-4 CI16 with `vld4_s16`, converts four lanes to FP32, loads cached templates with `vld2q_f32`, and maintains four stable FP32 partial lanes. Reduction, received/template energy, short and final FFTs, ceilings, residual selection, and final scoring remain FP64. All 16 frames and 64 symbols for both exact and control references remain.

Host and sanitizer tests cover all four rates, stride-2/stride-4 input, extreme CI16/template values, partial and full frame support, final-score tolerance, and residual-bin parity. ARM is cross-compiled only. Scientific recovery and target timing require qualification before promotion.
