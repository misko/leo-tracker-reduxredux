# Lower precision, integer FFT and compiler experiment

Compare new methods with the selected raw-FP32 fine FFT research baseline.
Keep final GLRT FP64 and the existing residual-boundary conditioned fallback.
No fine-FFT FP64 fallback is introduced. Use existing saved IQ only; no RF.

Independent experiments: genuine fixed-point FFT at the original transform
length and frequency grid; packed/scaled representations; compiler LTO and
local arithmetic improvements. FP32 FFT with quantized input is a quality
diagnostic only, never evidence of integer-compute speedup. Fixed-point plans
must account for scaling/packing, widened intermediate operations and overflows.
Global reassociation/fast-math, if tested, is explicitly approximate and cannot
claim to leave the final FP64 calculation unchanged.

First use the existing 32-dwell DS7 panel, all four rates/both edges, fixed
FP64 proposal coordinates, 704 windows and 843 standard hits. Compare output
with raw-FP32 fine FFTs, and independently score final detections against the
standard GLRT pipeline using the frozen same-window, one-to-one matcher:
margin >=0.025, <=2 samples and <=8 kHz. Report unmatched positives separately.
Packing cannot silently collapse candidate multiplicity or remove windows.

Measure viable variants serially on .15 CPU0 using the same four saved 2.5 MS/s
dwells as earlier ARM experiments (88 windows, 119 standard positives). Include
all per-window conversion, scale selection, allocation, planning and cleanup
in search CPU; file loading and initial workspace setup remain excluded as in
the reference. No concurrent RF or capture; no production/service changes.
Fewer floating operations or narrower lanes is not proof of less ARM CPU.

Expand a promising mode to the existing 704-dwell DS7 development subset with
the frozen FP32 proposal outputs, run actual GLRT and audit original-hit
recovery. Include per-rate counts. Repeat only promising ARM timing variants.
No universal precision/equivalence claim from empirical tolerance tests.
Keep new source/build/output directories immutable and preserve unrelated work.
Publish measured results, rejected variants, source/build hashes and next step
in the ARM progress index. Current selected baseline changes only if evidence
supports it; testing a variant alone does not promote it.
