# Packed CI16 by Q15 final-GLRT dot experiment

This experiment starts from the preferred final-reuse fine2 scorer. It adds a direct-CI16 entry point and quantizes the CFO-rotated exact/control templates once per executed final GLRT call into workspace-owned Q15 arrays. All 16 frames and 64 symbols remain. ARM stride-4 input uses `vld4_s16`; templates use `vld2_s16`; widening products are accumulated into signed 64-bit lanes. FP64 received/template energy, short spectra, ceilings, residual selection, and final scores remain unchanged.

The Q15 scale is derived once from the maximum exact/control template magnitude. Rotation preserves magnitude, so finite accepted templates cannot clip except for the explicitly saturated rounding endpoint. A 45-sample symbol has a worst-case complex-component accumulation below `2*45*32768*32768`, requiring 37 signed bits; int64 has ample headroom.

This changes matched-filter precision and requires recovery qualification. Host and sanitizer tests cover all rates, stride 2/4, saturation, extreme CI16/Q15 products, and a conservative quantization-error bound. ARM is cross-compiled only.
