# Original and compact v5 on the same hybrid waveform

The original no-repair v5 and compact phase-release both published when the offered tile omitted the simulated site by 1.500 km. Their estimates landed on the tile face. The frozen 20 m interior rule withheld both calibration arms and preserved their fitted endpoints as diagnostics. All three paths published in both arms when the tile contained the site. All three withheld on both donor-only offers. [Zero calibration figure](charts/c0/hybrid-v5-matched-waveform.png) · [Fitted calibration figure](charts/fitted_c/hybrid-v5-matched-waveform.png)

## Matched position and RF results

| Offer | Receiver | `c = 0` position error | Fitted `c` position error | RF RMS `c = 0` / fitted | Position wall |
|---|---|---:|---:|---:|---:|
| Containing | Original v5 | 1.032 km | 1.448 km | 15.955 / 15.665 Hz | 81.85 s |
| Containing | Compact phase-release | 1.036 km | 1.452 km | 15.955 / 15.665 Hz | 17.90 s |
| Containing | Compact 20 m interior | 1.036 km | 1.452 km | 15.955 / 15.665 Hz | 18.45 s |
| Near omitted | Original v5 | 1.565 km, false fix | 1.539 km, false fix | 17.178 / 17.089 Hz | 114.99 s |
| Near omitted | Compact phase-release | 1.570 km, false fix | 1.545 km, false fix | 17.173 / 17.083 Hz | 18.61 s |
| Near omitted | Compact 20 m interior | Withheld, 1.570 km forced | Withheld, 1.545 km forced | 17.173 / 17.083 Hz | 18.80 s |

The containing truth was 4.268 km inside its tile. The two compact fits were 3.369/3.096 km inside. Original and compact containing endpoints differed by 5.38/4.69 m, and their near-omitted endpoints differed by 17.94/24.85 m along the tile-face fit. On the containing offer, fitting `c` reduced the original RF RMS by 0.29 Hz while position error increased by 416 m. The compact paths show the same pattern. Conditional RF objective values, signed face distances and fit status are available separately from geographic error. [Per-offer, per-arm scores](scores.csv)

Each method used 604 gated hybrid observations and 20 Graph tracks. The original associated 286 observations per calibration arm on each positive-background offer. The donor-only detector also gated 345 of 1,536 probes from the archived background. No donor-only attempt reached an active-curvature fit and all three methods withheld 2/2 offers per arm. Donor-only supplies no simulated position to score. These are two offers on one background waveform. [Detector coverage and separate Gaussian control](../hybrid-site/README.md)

## Inputs, runtime and limits

The acquisition controller mixed the same simulated Qin pilot waveform into amplitude-normalized archived IQ slices for one synthetic site. A donor-only pass used the same archived slices with no injected pilot. The numerical comparison consumed complete stock wide-GLRT packets on both backgrounds, after 768 dual-antenna visits per background. The original and compact runs used the same bytes, 25 km offers, fixed causal clock, full received TLE history and track configuration. Original v5 used the earlier roof-parity regional validator adapter on the unchanged no-repair numerical core. The guarded compact package adds its already frozen terminal publication rule. [Original roof-parity receipt](../../receiver-core/v5-regional-reference/roof-retry/parity.json) · [Source and execution protocol](PROTOCOL.md)

All four original and eight matched compact attempts reached a terminal result. Original v5 ran in one-thread 3 GiB cgroups without swap under a 240 s deadline. Compact and guarded time receipts use the acquisition controller's predeclared caps and RSS accounting. The measured original CPU was 66.24 s containing and 99.98 s omitted, compared with 17.68 s and 18.17 s for phase-release. Times are factor-to-position on this host. The IQ mixing and detector stage has a separate timing ledger. Original and compact memory columns use different accounting. [Execution records](matched-positions.jsonl.gz) · [Independent runtime protocols](../hybrid-site/PROTOCOL.md)

The original and compact predictions sealed before the custodian released the site and offer roles. The four compared IDs distinguish the two backgrounds and two offers, with one underlying site. This tests the numerical path on a new simulated geometry over real recorded background. It supplies no survey of a newly measured receiver location and no evidence on arbitrary close-inside offers. [Original prediction seal](prediction-lock.json) · [Custodian score seal](../hybrid-site/score-lock.json) · [Matched score and chart seal](score-lock.json) · [Standard figure manifest](figures.json)

The preliminary source lock assumed the earlier public packet layout. The executed lock adds only the common config/TLE alias checks and authenticates the cutoff against the supplied native bracket because the new public offer rows omit an explicit cutoff. Both locks preceded numerical work, and the original controller request digest is unchanged. [Preflight source lock](preflight-source-lock.json) · [Executed source lock](source-lock.json)
