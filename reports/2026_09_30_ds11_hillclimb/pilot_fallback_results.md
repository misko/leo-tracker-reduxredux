# Reliability-gated pilot corrections fail two-scan replication

The fixed pilot/GLRT fallback retains the scan0 long-pilot gain but worsens
scan16. It fails the prospective requirement to improve both scans. Neither
the short arm nor the long arm supports advancement to wider confirmation.
No threshold is retuned, no geographic winner is selected per scan, and no
production model is changed.

| Scan | Original IID error | Short pilot with fallback | Long pilot with fallback |
|---|---:|---:|---:|
|0|765.072m|804.019m (+38.947m)|745.342m (-19.730m)|
|16|2153.140m|2135.687m (-17.453m)|2171.384m (+18.244m)|

Reference errors use the existing unsurveyed roof coordinate; all comparisons
remain exposed-site mechanism tests. Causal orbit inputs remain unchanged.
The long arm was the predeclared lead. Its small opposing changes nearly
cancel; an aggregate mean gain must not conceal failure to improve both scans.

The rule, frozen before scan0 stability measurements and all new position fits,
requires full and alternating-group pilot estimates inside their original
search range and group agreement within100 canonical Hz. Otherwise the original
GLRT frequency and timestamp remain. The100Hz scale comes from the existing
position likelihood, not a calibrated frequency-confidence interval. Both
arms and every localization observation are retained. Pilot acceptance is:

| Scan | Short accepted / proposed | Long accepted / proposed |
|---|---:|---:|
|0|48/111|111/111|
|16|72/124|119/124|

Scan0's new stability audit measures all111 excerpts in22.23seconds and exactly
replays its full estimates. All111 long corrections pass, so that arm's result
exactly reproduces the earlier nominal-support fit; it is not another independent
gain. Scan16's five rejected long corrections retain original GLRT evidence.
Short-arm fallback reasons are63 group disagreements on scan0, and50 group
disagreements plus two boundary failures on scan16. Long-arm scan16 rejects
four disagreements and one alternating-group boundary failure.

All16 fits qualify and exit0, with6.21–14.73second per-fit wall times, at most
three numerical workers, and no retry or recovery. Highest-training-score
selections for both arms on both scans are sealed before either geographic
assessment. Maximum within-arm EN disagreement across starts is2.17mm.
Conditional MAP satellite assignments do not change in either scan or arm.
All corrected candidate predictions exactly match independent scalar state
interpolation; held-row predictions match original timing exactly. Verification
also confirms zero correction and zero time shift on every fallback row.
The28 component tests cover frequency units, acceptance boundaries, preservation
of original measurements, and sealing both scans before geography.

The source-bound [combined outcome](pilot_fallback_outcome.json), individual
[scan0 outcome](pilot_fallback00/outcome.json), [scan16 outcome](pilot_fallback16/outcome.json),
and [protocol](pilot_fallback_protocol.md) preserve all decisions and attempts.
Scan0 plan SHA256 is
`a113a1a712ed9cd0b74fc39cc1c648b978bed1c94b77f141c0a049293ff97055`;
scan16 is
`320ed6ac7eee031e4153e400bbe7261de1e9676630ba556f60af62063c57bd0e`.
The original failed two-arm scan16 experiment remains unchanged and separate.

Better pilot prediction and stability are insufficient to rank geographic
accuracy here. These corrections move errors by tens of meters, while deleting
the influential conditional sources previously moved positions by kilometers.
This does not prove an orbit-error floor or invalidate waveform work. It does
argue against further threshold tuning on these two exposed errors. The next
useful step is a diagnostic that separates source-common residual structure
from receiver/track-specific structure and competing GLRT interpretations,
before granting additional nuisance freedom or reweighting those sources.
