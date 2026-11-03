# Qualified GLRT CPU sampling

The unchanged ordinary ungated benchmark processed 32 evenly spaced DS9
dwells eight times (256 calls) under a 60-second sampler limit. All scientific
rows, including candidates and execution diagnostics, match the saved ARM
reference. Sampling collected 5,275 instruction pointers with no lost samples;
the child completed normally. Repetition supplies profile density, not new
scientific evidence or sustained-cadence qualification.

The executable hash matches the locally symbolized binary. `maps.txt` records
its actual PIE load address. `profile.json` maps IPs to sized executable
symbols; shared libraries are grouped by module. Sampling includes setup and
input preparation and does not provide isolated function runtimes.

Largest sampled symbols: full search 1,020; final GLRT 712; FFT codelet t3fv_25
589; proposal 501; input preparation 437; coarse FP32 382. Other FFT codelets
and the dynamic double-precision FFT library also contribute substantially.
Input preparation and fine FFT execution merit bounded separate experiments.

A separately built debug executable has identical `.text` bytes and matching
section addresses. Its symbols therefore provide source attribution for the
original samples; the debug binary itself was not timed. Source profile and
inline stacks are retained. Of 319 samples attributed to `power()`, 234 are
received-sample energy accumulation in `full_conditioned_scores`, 28 are fine
FFT received energy, 22 are fine template energy, and 28 are final GLRT spectral
power. The remainder is small template/proposal work. This directs the next
experiment toward exact reuse of CI16 energy prefixes in conditioned scoring,
with explicit provenance and numerical checks before enabling that path.
