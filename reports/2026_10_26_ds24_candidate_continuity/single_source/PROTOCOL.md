# A known-single-source control for false extra paths

The original six single-source closure receiver outputs contain gate-passing
secondary peaks about 11.23 kHz from the injected CFO at a different frame
epoch; the right-boundary sampled control also has nearby alternate estimates.
This motivates a separately frozen negative control for the new path selector.
It does not change or extend the old two-source sequences and does not tune the
selector after their outcomes. The selector is already frozen at protocol
565428a8fd05e89728fedc331a31672d84ca2da4aa775ce81b7fdfdec86c76d9.

Generate one source only, with the unchanged deployed sampled-template law
and rounded frame anchors from the preceding experiment. At visits t=0..23 s,
use 20 ms of 10 MS/s IQ, CFO=100000+200*T Hz at global sample time T, amplitude
1000, initial phase0.3 radians, integer frame epoch127. Its carrier integrates
the linear instantaneous CFO. It is a pilot-only inverse-model control, not
a realistic transmitted waveform. Integer-second visit spacing contains750
nominal frames. Two receiver streams have the same source and independent
complex Gaussian noise, RMS300, using SeedSequence([2026102603, visit]). This
new fixed seed is not rerolled. Quantize once to int16 and require no clipping.

Run the unchanged historically deployed detector on all24 paired windows;
retain all peaks, gate failures and missed calls. No input is a recording and
no provider/capture/UTC authority is fabricated. No IQ files or RF collection
are needed. Each detector call has at most20 seconds, and all preparation,
tests and detector execution share a120-second cumulative cap. No retries or
fallback template. Source/environment identity must match before and after.

Only after the response-only RF seal, apply the exact already frozen winner,
CFO-only and epoch+CFO path policies through their existing row port, using
A's remaining original300-second budget. Preserve the original graph quality
checks. Twenty-four visits allow the unchanged support check to be evaluated,
but no passing result is assumed. Report source-proximity, unmatched paths,
candidate hypotheses versus unique windows, and all quality flags. A second
coherent path from this input is not a second physical emitter. Truth is used
for evaluation only, never candidate or parameter selection. No satellite,
position or admission claim follows from this test.
