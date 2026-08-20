# Standard-v2 analysis path

How one committed recording becomes GLRT-64 trajectory evidence: the stage
graph, the per-sample arithmetic, and the feedback loop that replays the
original bytes against a fitted CFO polynomial.

This is a reference for the pipeline as implemented. It is not a plan.
`standard_pipeline_plan.md` holds the frozen architecture and delivery order,
`standard_pipeline.md` holds the investigation working record, and
`docs/standard-pipeline-handoffs/` holds remaining execution work. Where this
document and those disagree about current behaviour, the code wins and this
document is wrong; report it.

Everything below is candidate-only evidence. Nothing here establishes Starlink
attribution, target presence, or payload recovery. See
[What is not claimed](#what-is-not-claimed).

## Contents

- [Two lanes](#two-lanes)
- [Run lifecycle](#run-lifecycle)
- [The ten path stages](#the-ten-path-stages)
- [Probe geometry](#probe-geometry)
- [Common acquisition](#common-acquisition)
- [The detector bank](#the-detector-bank)
- [GLRT, exactly](#glrt-exactly)
- [Known-pilot QAM](#known-pilot-qam)
- [Tracking and trajectory feedback](#tracking-and-trajectory-feedback)
- [Publication and the read-only UI](#publication-and-the-read-only-ui)
- [What is not claimed](#what-is-not-claimed)
- [Known gaps](#known-gaps)
- [Code map](#code-map)
- [Reference recording](#reference-recording)

## Two lanes

Analysis runs in two places, and they are not competing implementations.

- The **production lane** is the 12-analyzer registry
  `production_standard_v2_registry`, executed by leased workers against
  PostgreSQL job state, publishing immutable JSON products into the artifact
  store.
- The **exploratory lane** is the scripts under `tools/`, which read the same
  recordings directly from `/srv/bulk/leo` and emit PNG/CSV/JSON into
  `artifacts/`.

Both call the same numerical kernel in `leo.analysis.starlink` and
`leo.analysis.qam`: the same acquisition, the same eight detectors, the same
trajectory fitter. The production lane adds contracts, digests, lineage and
bounded resource classes. The exploratory lane adds comparison panels and runs
ahead on track linking; see [Code map](#code-map).

Everything below describes the production lane.

## Run lifecycle

```text
ACQUISITION (local CLI)          PROCESSING (leased, isolated)              PRESENTATION
──────────────────────────  ──────────────────────────────────────────  ─────────────────
┌──────────┐   CI16   ┌───────────────┐  compile  ┌─────────────┐
│ 2x Pluto+│ ───────► │   immutable   │ ────────► │ expanded    │
│ 4 RX     │          │   bundle      │           │ plan        │
└──────────┘          │ manifest+zstd │           │ 43 nodes    │
                      └───────┬───────┘           └──────┬──────┘
                              │                          │ claim lease
                              │                   ┌──────▼──────┐   publish  ┌────────────┐
                              │  verified IQ      │   leased    │ ─────────► │47 products │
                              └──────────────────►│   workers   │            │digest-addr │
                                 re-read per      │1 proc/node  │            └─────┬──────┘
                                 stage, digests   └─────────────┘                  │
                                 checked                 ▲                         │
                                                         │                   ┌─────▼──────┐
                                                  ┌──────┴──────┐            │ API v2 +   │
                                                  │seal &promote│ ◄───────── │ React UI   │
                                                  │run manifest │            │ read-only  │
                                                  └─────────────┘            └────────────┘
```

An operator runs `leo process reprocess <session>`. That path verifies the
on-disk bundle against the catalog manifest digest, checks Standard eligibility
(committed, healthy, not tag-excluded), and requires the configured pipeline
release to be the exact deployed source SHA. Only then does
`compile_standard_run_plan` expand the **manifest** — not configuration — into
**43 job nodes**: ten stages for each of four receiver paths, one reducer per
radio, and one paired reducer because this manifest has exactly two streams.
Product inventory is 11 per path x 4 paths + 2 radio reports + 1 paired report
= **47**.

A worker claims one node under a lease, renews a heartbeat, and runs the
analyzer inside a separate process with a wall-time budget and an output byte
budget chosen by the stage resource class. Products are staged locally first,
validated against the analyzer declared outputs, then materialized and committed
to the catalog in one transaction bound to the live lease. When every node has
succeeded, `finalize_run` seals a run manifest and atomically promotes it as the
session current analysis.

## The ten path stages

```text
                    ┌──── OBSERVABILITY (every sample) ────────────────┐
                    │                                                  │
              ┌────►│ ▣1 quality ──► ▣2 power ──► ▣3 waterfall         │──┐
              │     │  clip/cover     1s dBFS      512x256 tiles       │  │
 ┌─────────┐  │     └──────────────────────────────────────────────────┘  │
 │ □0      │  │                                                           ▼
 │input-   ├──┤                                                    ┌─────────────┐
 │ bind    │  │     ┌──── DETECTION (20ms of each 50ms) ──────────┐ │ □8 report  │
 └─────────┘  │     │                                              │ │ status+dig │
              └────►│ □4 sched ──► ▣5 pilot-scan ──► □6 bank ──► ▣7│ └──────┬─────┘
                    │  1200 probes  acquire+8 det.   d1/d2/d3  feedback     │
                    │                    │                        ▲        ▼
                    │                    └── baseline margins ────┘  ┌─────────────┐
                    └───────────────────────────────────────────────┐│ □9 present. │
                                                                     │ UI payload  │
  ▣ = reads verified IQ    □ = upstream products only                └─────────────┘

 resource: STREAMING│STREAMING STREAMING HEAVY│CPU HEAVY MEMORY HEAVY│CPU CPU
```

Declared in `leo/pipeline/topology.py` as `_PATH_STAGES` plus 22 explicit edge
slots. The split at stage 0 is deliberate: observability (1-3) and detection
(4-7) never consume each other products, so a waterfall failure cannot
invalidate a pilot scan. Stage 7 depends on both 5 and 6 because it needs the
original per-probe margins to compute a delta against.

Cross-stage validation is aggressive:

- Each stage validates predecessor geometry against the IQ it opens — sample
  rate, declared sample count and receiver inventory must agree, or the stage
  raises rather than producing a mismatched product.
- Stage 6 recomputes `canonical_digest` of the pilot-scan document and refuses
  unless the bank it was handed cites that exact digest.
- Stage 8 re-derives every dependency digest a third time through
  `verify_standard_source_bindings`.

Two reducers close the run. `radio-scientific-report` collects the two path
reports on one stream. `paired-scientific-report` collects the two radio reports
and binds them to the synchronization inventory digest, which carries measured
start skew and the `phase_coherent` flag from the manifest.

## Probe geometry

```text
DWELL - 60 s - 150,000,000 samples
[█─────────────────────────────────────────────────────────────────]  60x 1s coarse windows
 └─┐
   ▼
COARSE WINDOW - 1 s - 2,500,000 samples - 20 subwindows
[██···██···██···██···██···██···██···██···██···██···██···██···██···]
 ██ = leading 20 ms analyzed        ··· = 30 ms skipped
 └─┐
   ▼
PROBE - 20 ms - 50,000 samples - 15 pilot frames
[████|····|····|····|····|····|····|····|····|····|····|····|····|·]
 frame period = fs/750 = 3333.33 samples - epoch unknown within one period
 └─┐
   ▼
FRAME - 300 known pilot symbols (index 2..301) - 11 samples each - 8 subcarriers
[▓░░░▓░░░▓░░░▓░░░▓░░░▓░░░▓░░░▓░░░ ... ░░░▓]
 └──── GLRT-64 aperture: symbols 2..65, 277 us ────┘
 ▓ = the 8 anchor-8 symbols, spread over 1.32 ms
```

"What happens to each analyzed sample" has two different answers, because the
observability chain and the detection chain sample the dwell differently.

**Every** sample reaches stages 1-3. Quality widens each CI16 component to
int64 and accumulates clip counts and I/Q extrema. Power accumulates `I^2+Q^2`
into one-second bins normalized by `32768^2` and reports dBFS. The waterfall
runs Hann-windowed 1024-point FFTs that never cross a declared gap, folding
into a grid of 512 time bins by 256 frequency bins.

**Two fifths** of the samples reach the pilot detector. The schedule at stage 4
divides the dwell into one-second coarse windows, each coarse window into twenty
50 ms subwindows, and analyzes only the leading 20 ms of each — 1200 probes
across a 60-second dwell, each 50,000 samples, each identified by a digest over
its geometry so the scan at stage 5 can be proven to have consumed exactly the
scheduled probes and nothing else.

At 2.5 MS/s every duration is integral, and `build_probe_schedule` raises if it
is not:

| Quantity | Value at 2.5 MS/s |
|---|---|
| OFDM symbol | 4.4 us = 11 samples |
| Frame period | 1/750 s = 3333.33 samples, template 3333 |
| Pilot content | symbols 2..301 = samples 22..3321 |
| Probe | 20 ms = 50,000 samples = 15 supported frames |
| Epoch search space | one frame period = 3333 bins |

The reference waveform is not a guess. `leo/analysis/starlink/templates.py`
carries the published Qin et al. Appendix-A constants — sixteen 600-bit
hexadecimal integers encoding 300 base-4 states for each of eight edge-pilot
subcarriers — and synthesizes one frame by summing those QPSK states over
subcarriers `528..535` (lower edge), shifted to pilot-band center.

The negative control is the same construction with `symbol_roll = 17`: the
identical 300 x 8 state matrix cyclically rotated by 17 symbols. Same amplitude
statistics, same subcarrier layout, same energy — the wrong code. Every detector
that supports a control is scored against both templates and reports the
difference.

## Common acquisition

This is the stage that makes the eight detector curves comparable.
`acquire_symbolwise` runs once per probe and produces up to eight retained
timing/frequency basins. Each detector is then evaluated on the same IQ at the
same epoch and the same CFO. They are confirmers conditioned on a common
acquisition, not eight independent blind searches.

```text
per retained basin, repeated
     ┌───────────────────────────────────────────┐
     ▼                                           │
┌──────────────┐   ┌─────────────┐   ┌───────────────┐   ┌──────────────┐   ┌────────────────────┐
│ coarse fold  │──►│retain basins│──►│  fine CFO     │──►│ conditioned  │──►│ adjudicate & rank  │
│11 CFO x3333ep│   │local pks ≤8 │   │321 pts@500 Hz │   │41 pts@100 Hz │   │verify:150 odd sym  │
│12 anchor sym │   │≥20 samp OR  │   │150 even syms  │   │whole 3333-sam│   │control:same,roll17 │
│±400k / 80k Hz│   │ >80 kHz sep │   │+quad peak     │   │frame template│   │margin = ver - ctrl │
└──────────────┘   └─────────────┘   └───────────────┘   └──────────────┘   └─────────┬──────────┘
                                                                                      ▼
                                                                            ┌────────────────────┐
                                                                            │ top 4 basins       │
                                                                            │ epoch + abs CFO    │
                                                                            │ → detector bank    │
                                                                            └────────────────────┘
```

The statistic every acquisition step maximizes is the historical normalized
noncoherent frame score:

```text
             1      | < p[S],  x[e + fT + S] * exp(-j2*pi*f*n/fs) > |
S(e, f) =   ---  SUM ------------------------------------------------
             F     f      sqrt( ||p[S]||^2 * ||x[e + fT + S]||^2 )

e = epoch   f = trial CFO   T = fs/750 frame period   S = symbol subset
magnitude taken per frame, then averaged  ->  noncoherent across frames
```

The coarse stage is a full matched filter, not a sparse probe. For each of 11
CFO hypotheses the entire 50,000-sample probe is derotated once, then twelve
11-tap references are convolved over it in `valid` mode and the normalized
magnitudes are folded modulo the frame period into 3333 epoch bins.

Acquire symbols (even 2..300) and verify symbols (odd 3..301) are **disjoint by
construction**, so the ranking statistic is measured on symbols the search never
optimized against.

Candidates are ranked by `verify_minus_control_margin`, then verify score, then
conditioned exact score, then acquire score, with ties broken toward smaller
`|CFO|` and earlier epochs. A basin with fewer than two supported frames is
discarded outright.

**Frequencies are baseband and uncalibrated.** `_baseband_prior` constructs an
explicitly uncalibrated receiver prior with `center_hz = 0.0`, so
`absolute_cfo_hz = 0 + residual`. Products label this as
`frequency_coordinate: baseband_cfo_hz` and
`frequency_reference: uncalibrated_prior`. Absolute frequency requires the
separate calibration lane.

The v2 scan keeps the top four basins per probe and scores all eight detectors
on each, so one probe contributes up to 32 observations rather than 8. That is
the bounded multi-candidate contract the working record calls a prerequisite for
real multi-target tracking. The v1 winner-only path remains as
`scan_legacy_pilot_detections`.

## The detector bank

Given a fixed epoch and CFO, `_conditioned_correlation_workspace` computes the
entire evidence surface exactly once:

```text
for frame f = 0..14, symbol s = 2..301:
  n      = e + round(f * fs/750) + round(s * fs * 4.4e-6) + [0..10]
  x~[n]  = x[n] * exp(-j*2*pi * f_hat * n / fs)     derotate by acquired CFO
  c[f,s] = SUM conj(p_exact[n_local]) * x~[n]       11-tap complex correlation
  k[f,s] = SUM conj(p_roll17[n_local]) * x~[n]      same, wrong code
  rho    = |c[f,s]|^2 / (||p||^2 * ||x~||^2)        normalized power in [0,1]
```

Every detector is a different way of combining that same `c` matrix over a
different symbol subset — which is exactly a choice about how much phase
coherence to assume across the aperture.

| Detector | Symbols | Aperture | Combination | Residual CFO |
|---|---|---|---|---|
| `edge_tracker` | 2..301 (300) | 1.32 ms | mean of rho, no coherent combining | none |
| `symbolwise` | odd 3..301 (150) | 1.32 ms | acquisition held-out verify score | none |
| `anchor8` | 8 spread | 1.32 ms | fully coherent, nu pinned to 0 | none |
| `differential16` | 2..17 (16) | 66 us | lag-1 products, phase-ramp immune | arg(SUM)/2*pi*dt |
| `differential32` | 2..33 (32) | 136 us | lag-1 products, longer run | arg(SUM)/2*pi*dt |
| `glrt32` | 2..33 (32) | 136 us | coherent, maximized over nu | argmax nu |
| `glrt64` | 2..65 (64) | 277 us | coherent, maximized over nu, primary | argmax nu |
| `qam_accuracy` | 2..301 (300) | 1.32 ms | full LS demodulation, hard decisions | phase-slope fit |

The anchor-8 symbol set is `[2, 45, 87, 130, 173, 216, 258, 301]`.

Read the table top to bottom and the trade is visible. `edge_tracker` assumes
nothing and gains nothing beyond incoherent averaging; it is the most robust and
least sensitive. `anchor8` assumes phase coherence across eight symbols spread
over 1.32 ms — large coherent gain when the CFO is right, and a statistic that
collapses when it is off by a few hundred hertz, because the lever arm is that
long. The differential pair cancels the phase ramp entirely and therefore cannot
benefit from it, but recovers the slope as a CFO estimate. The GLRT pair does
both.

All score statistics are normalized by the same coherent ceiling
`SUM_f (SUM_s |c[f,s]|)^2` — the value the numerator would take if every symbol
in every frame added in perfect phase — so each lands in [0,1] and exact and
control scores are directly subtractable. Only `qam_accuracy` has no control;
its margin is the accuracy itself.

Each detector reports `tracking_cfo_hz = acquired_cfo_hz + residual_cfo_hz`. For
anchor-8, edge-tracker and symbolwise the residual is zero by construction, so
those three contribute only a score at the acquisition frequency. The
differential and GLRT families contribute a refined frequency of their own. That
distinction propagates into the tracker.

## GLRT, exactly

The generalized likelihood ratio here is over a single unknown: the residual
carrier frequency offset `nu` left after acquisition. Under the alternative the
pilot is present and each symbol correlation carries a common complex amplitude
rotated by `exp(j*2*pi*nu*tau_s)`; under the null they are independent noise.
Maximizing the likelihood over the unknown amplitude and phase gives a
matched-filter magnitude; maximizing over `nu` gives a search across a frequency
grid. The result is a periodogram of the correlation sequence.

```text
symbol lags, taken from the first frame - all frames share the geometry
  tau_s = t_s - t_0                       s in S,  |S| = 32 or 64

phase bank: 512-point grid from fftfreq(512, d = 4.4 us)
  nu_k in [-113.64, +113.19] kHz,  d_nu = 443.9 Hz

coherent within a frame, noncoherent across frames
  T(nu_k) = SUM_f | SUM_{s in S}  c[f,s] * exp(-j*2*pi*nu_k*tau_s) |^2

normalize by the coherent ceiling and maximize
  G  = max_k T(nu_k) / SUM_f ( SUM_{s in S} |c[f,s]| )^2     statistic in [0,1]
  df = nu_(argmax_k T)                                        residual CFO

the control uses the identical phase bank on the rolled matrix k[f,s]
  margin = G_exact - G_control
```

```text
 c[f,s]           x exp(-j2pi nu tau)  SUM over symbols      SUM over frames      peak
 15x64 matrix     512 trial nu         then | . |^2          / ceiling            -> G, df
┌──┬──┬──┬──┐    ┌──────────────┐    ┌──┐                  ┌─────────┐         ▲   ╱╲
├──┼──┼──┼──┤    │ ∿∿∿∿∿∿∿∿∿∿∿∿ │    ├──┤                  │ T(nu)/C │         │  ╱  ╲__
├──┼──┼──┼──┤ ─► │ ∿∿∿∿∿ ∿∿∿∿∿  │ ─► ├──┤ ──────────────►  │         │  ─────► │_╱      ╲__
├──┼──┼──┼──┤    │ ∿ ∿ ∿ ∿ ∿ ∿  │    ├──┤                  └─────────┘         └────┬──────►
└──┴──┴──┴──┘    └──────────────┘    └──┘                                      -113k│df +113k
rows=frames      one ramp per nu     coherent gain         noncoherent across
cols=symbols     d_nu = 444 Hz       lives here            frames, 1.33 ms apart
```

The one performance decision in this diagram is where the coherent sum stops.
Summing across symbols inside a frame is safe: 277 us of aperture at GLRT-64,
over which Doppler rate is negligible. Summing across frames is not, because
consecutive frames are 1.33 ms apart and the pilot absolute phase between them
is not modelled, so frames combine as magnitudes. The statistic therefore grows
with symbol count but only as `sqrt(F)` with frame count.

Anchor-8 is literally the `nu = 0` slice of the same statistic:
`SUM_f |SUM_s c|^2 / SUM_f (SUM_s |c|)^2`. Same numerator form, same ceiling,
`nu` pinned.

### Why GLRT-64 is the primary lane

Doubling the aperture from 32 to 64 symbols buys roughly 3 dB of coherent gain
and halves the width of the peak in `nu`, which is what makes the residual-CFO
estimate precise enough to track. The next doubling is not free: at 128 symbols
the aperture reaches 563 us and fitted CFO curvature starts to smear the
coherent sum, and the 443.9 Hz grid spacing — set by the 512-point transform
over the 4.4 us symbol pitch — stops being the limiting error. Sixty-four
symbols is where the aperture is long enough to estimate frequency well and
short enough that a constant-frequency model still holds inside it.

This is policy in code: `select_trajectory_representatives` only replays a
trajectory family that contains a GLRT-64 member, and skips any family that does
not. The other seven detectors remain in the products as corroborating
diagnostics.

## Known-pilot QAM

The other seven detectors correlate against a template. QAM inverts the OFDM
model instead. For each symbol the 8 pilot subcarriers are recovered from the 11
available samples by a cached pseudo-inverse of the 11 x 8 exponential matrix.
The solve is geometry-only, so it is computed once per (rate, symbol) and reused
for every frame of every probe.

```text
A[n,c] = exp(j*2*pi*f_c*(t_n - T_cp)) / sqrt(8)    11 x 8, cached by geometry
y[s]   = pinv(A) * x~[symbol s]                    8 recovered subcarrier symbols

residual CFO from the unwrapped phase slope across the 300 symbols
df <- median over frames of d(arg y*conj(p))/dt / 2*pi,  clipped to +/-2 kHz

frames combined by quality weight, then equalized out of sample
w_f  proportional to |SUM y*conj(p)|^2 / SUM |y|^2,  clipped at 4 x median
H    = mean over EVEN symbols of y*conj(p)    -> equalizes ODD symbols
H'   = mean over ODD  symbols of y*conj(p)    -> equalizes EVEN symbols

accuracy = fraction of hard decisions matching the published states
EVM      = rms( equalized - expected )
```

Two details make the accuracy honest. The channel estimate is cross-fit: even
symbols train the equalizer that scores odd symbols and vice versa, so a symbol
is never equalized by an estimate that used it. And the constellation is the
published one, `exp(0.5j*pi*(state + 0.5))`, QPSK rotated 45 degrees, with hard
decisions compared against the Appendix-A states rather than against the
receiver own decisions.

QAM has no rolled control in the bank. Its margin is its accuracy, gated
separately in the tracker at 0.60 high and 0.45 low rather than by a noise-tail
estimate.

## Tracking and trajectory feedback

Stage 6 flattens the scan into `TrajectoryObservation` records — one per
(probe, basin, detector), each carrying time, `tracking_cfo_hz`, score, control
and margin. A 60-second dwell at four basins and eight detectors yields up to
38,400 observations, which the bank partitions **by detector** and fits
independently. Nothing is fused at this stage; every detector family gets its
own tracks, and the disagreement between them is itself evidence.

```text
FIT - no IQ access
┌──────────┐  ┌──────────────┐  ┌───────────────┐  ┌────────────┐  ┌──────────────┐  ┌─────────────────────┐
│  gate    │─►│    seed      │─►│    merge      │─►│  hard EM   │─►│ fit d1/d2/d3 │─►│ dedup into families │
│low: m≥0  │  │RANSAC lines  │  │gap ≤ 1.1 s    │  │reassign +  │  │polyfit + RMS │  │≥70% overlap of the  │
│high: 5σ  │  │in 1 s windows│  │dslope≤20kHz/s │  │refit ≤12   │  │BIC per track │  │shorter track AND    │
│of the    │  │≥5 pts and    │  │endpoint-      │  │iterations, │  │≥1.5 s        │  │median |df| ≤ 5 kHz  │
│neg. tail │  │≥2 high pts   │  │predicted      │  │clutter drop│  │duration      │  │repr. MUST be GLRT-64│
└──────────┘  └──────────────┘  └───────────────┘  └────────────┘  └──────────────┘  └──────────┬──────────┘
                                                                                                 │
      ┌──────────────────── ≤16 family representatives, coefficients only ────────────────────────┘
      ▼
REPLAY - re-reads the immutable recording, one bounded second at a time
┌──────────────┐  ┌────────────────────┐  ┌──────────────┐  ┌──────────────────┐  ┌────────────────────┐
│ original IQ  │─►│ integrate to phase │─►│   dechirp    │─►│ narrow reacquire │─►│ paired margin delta│
│ same probes, │  │phi=int polyval(a,t)│  │x*exp(-j2pi   │  │±20 kHz around 0  │  │corrected - baseline│
│ same digests │  │analytic via polyint│  │  *phi(t))    │  │2 basins retained │  │per probe, per det. │
│ re-read      │  │continuous across   │  │absolute      │  │then all 8 detect.│  │→ GLRT-64 table     │
└──────────────┘  │probes              │  │session time  │  └──────────────────┘  └────────────────────┘
                  └────────────────────┘  └──────────────┘
```

### The gate is measured, not configured

For every detector except QAM, the high gate is derived from the data. The
observations with **negative** margin — where the wrong code scored higher than
the right one — are treated as the null sample, a robust sigma is estimated as
`median(|margin|) / 0.6745`, and the gate is set at 5 sigma. A detector that
never produces a negative margin gets an infinite gate and contributes no high
points at all, which is the conservative failure.

### Seeding, merging and the EM step

Within each one-second window the seeder tries every pair of low-gate points at
least 0.15 s apart, draws the line through them, counts inliers within the
residual gate (2.5 kHz for the CFO-estimating families, 8 kHz for the rest), and
keeps the line with the most inliers, then the most high points, then the lowest
RMS. Seeds merge only forward in time and only when the gap, the slope
difference, the endpoint-prediction residual and the combined residual RMS all
pass — greedily, lowest cost first, until nothing more can merge. Survivors
shorter than 1.5 s are discarded. Hard EM then reassigns every low-gate
observation to its nearest surviving model within the residual gate and a 0.35 s
time extension, refits, and repeats until the assignment stops changing or
twelve iterations elapse.

Governing values from `default_trajectory_bank_config()`:

| Bound | CFO-estimating families | Other families |
|---|---|---|
| Local and final residual gate | 2500 Hz | 8000 Hz |
| Minimum local points | 5 | 6 |
| Minimum high points | 2 | 2 |
| Maximum merge gap | 1.10 s | 1.00 s |
| Endpoint gate + growth | 4000 Hz + 3000 Hz/s | 12000 Hz + 5000 Hz/s |
| Maximum slope difference | 20 kHz/s | 30 kHz/s |

CFO-estimating families are `differential16`, `differential32`, `glrt32` and
`glrt64`. Shared bank bounds: local window 1.0 s, minimum final duration 1.5 s,
EM extension 0.35 s, at most 12 EM iterations, at most 256 trajectories,
deduplication overlap 0.70 and frequency gate 5000 Hz, degrees 1/2/3. QAM uses a
fixed 0.60 high and 0.45 low gate; all other detectors use low gate 0 and the
measured 5 sigma high gate.

Each surviving group is fitted at degree 1, 2 and 3 — the same points, three
models — and `BIC = n*ln(sigma^2) + k*ln(n)` is recorded next to RMS
specifically so the cubic guaranteed residual reduction is not read as evidence
that the extra curvature parameter earned its place.

### Families exist to stop combinatorial replay

Eight detectors times three degrees times several tracks produces dozens of
near-duplicate curves. Two trajectories join a family when they overlap by at
least 70% of the shorter one **and** their median frequency difference over the
overlap is within 5 kHz. On the reference recording, 60 method/degree hypotheses
collapsed to 4 distinct families, of which 3 were replayed.

### The loop closes on the original bytes

`replay_pilot_trajectories` re-streams the same scheduled probes and dechirps
each one in place, so no full corrected dwell is ever materialized and each
replay costs one extra pass rather than one extra recording per hypothesis. The
phase model is the analytic integral of the fitted CFO polynomial evaluated at
absolute session time, so the correction is phase-continuous across probes.

A rise in median margin after correction says the CFO evolved coherently along
the fitted curve over that interval. It does not say the source is Starlink, and
the paired null is retained beside it. On the reference recording the GLRT-64
quadratic over 6.2-9.7 s raised median GLRT-64 margin by 0.326 and median QAM
accuracy by 0.219; the symbolwise-only trajectory over the same span produced
essentially no gain. That paired result is why both hypotheses are preserved.

## Publication and the read-only UI

Stage 8 builds the terminal path report. It re-validates that the pilot results
exactly cover the ordered probe schedule, that the method inventory matches the
scored candidates, that every source binding chain resolves, and that no
scientific document contains run-owned identity — `run_id`, `job_id`,
`scope_key` and release IDs are forbidden inside reusable science. The report
status is then a mechanical function of coverage and truncation:

| Condition | Status |
|---|---|
| no observed samples, or no certificates | `insufficient_data` |
| observed sample count differs from declared | `partial` |
| every probe insufficient | `insufficient_data` |
| some probes insufficient | `partial` |
| schedule, candidate or trajectory truncation occurred | `partial` |
| complete search, no probe result | `no_result` |
| complete search, no retained trajectory | `no_result` |
| complete bounded search with retained trajectories | `complete` |

Stage 9 packages the power timeline, waterfall tiles, pilot scan, bank, feedback
and GLRT-64 table into one presentation product bound to the report digest. The
API exposes six view kinds — `quality`, `power`, `waterfall`, `glrt64`,
`cfo_trajectory`, `qam` — as bounded JSON, and the four scientific ones also as
server-rendered PNGs from a disk cache keyed by a subject-identity digest. The
GLRT-64 PNG renders with its CFO-trajectory companion so response and frequency
share an axis. Power and quality deliberately have no PNG endpoint.

Before any view is returned, the repository re-verifies the declared source
extrema against the underlying product and rejects the response with 503 if the
projection disagrees. The browser receives presentation contracts only; it never
reads a scientific product and cannot invent resolution, which is why the
waterfall stage is configured at 512 time bins by 256 frequency bins rather
than the kernel default.

## What is not claimed

Every scientific document carries `candidate_only: true`,
`specificity_claimed: false` and `payload_decoded: false`, and those flags are
load-bearing.

- **Frequencies are uncalibrated.** The receiver prior is centred at zero, so
  every CFO in the products is baseband offset from the applied tune.
- **No detection threshold is calibrated.** The 5 sigma negative-tail gate, the
  2500 Hz residual gates and the 2500 Hz fit-quality flag are working values
  from one recording, not thresholds derived from labelled evidence.
- **Nothing establishes Starlink specificity.** A high margin says the received
  signal matches the published Qin edge-pilot code better than the same code
  rolled by 17 symbols. That is a code match, not an attribution.
- **Only known synchronization symbols are demodulated.** The QAM path recovers
  published pilot states. No user payload is touched anywhere in this
  repository.
- **Multi-target tracking is not qualified.** The v2 scan retains four basins
  per probe, which is the prerequisite; the tracker has not been shown to
  separate two genuinely simultaneous tracks.
- **Cross-radio phase is not coherent.** The reference manifest reports degraded
  best-effort synchronization with `phase_coherent = false`; the four-path
  shared clock compares second-scale trajectories only.

## Known gaps

- **Durable reuse is contracted but not wired.** `leo/pipeline/derivation.py`
  defines a full stage-derivation key — algorithm version, configuration digest,
  environment digest, implementation digest, scope, and the compressed and
  uncompressed chunk-closure digests of the exact selected raw byte interval —
  and the catalog enforces `legacy | computed | reused` membership. But
  `ProcessingService.run_once` registers products with the default `legacy` mode
  and never consults a prior derivation, so every stage recomputes on every run.
  Handoff 04 covers the remaining work.
- **Two feedback analyzers coexist.** The single-stage winner-only
  `TrajectoryFeedbackAnalyzer` in
  `leo/analysis/starlink/trajectory_feedback.py` is still registered by the
  legacy long-dwell registry in `leo/analysis/adapters.py`. Standard-v2 uses the
  split scan/bank/feedback form with four basins per probe. The two lanes must
  not be conflated when comparing outputs.
- **There is no multi-target assignment policy.** Bounded multi-candidate
  evidence does reach the tracker — up to four basins per probe survive the
  product round-trip and `trajectory_observations` emits one observation per
  (probe, basin, detector). What is missing is everything above linking:
  prediction, gated assignment, track birth and death, merge and split, and an
  explicit gap policy. The current fitter is a per-detector greedy merge plus
  hard EM with no cross-detector fusion, so it can reject outliers and link
  branches but has not been shown to separate two coexisting real tracks.

## Code map

| Concern | Path | Entry point |
|---|---|---|
| Pilot template and control | `leo/analysis/starlink/templates.py` | `qin_edge_pilot_frame` |
| Acquisition cascade | `leo/analysis/starlink/acquisition.py` | `acquire_symbolwise` |
| Detector bank | `leo/analysis/starlink/pilot_methods.py` | `conditioned_pilot_method_scores` |
| GLRT kernel | `leo/analysis/starlink/pilot_methods.py` | `_glrt_pair` |
| Known-pilot QAM | `leo/analysis/qam/pilot.py` | `analyze_pilot_qam` |
| Track fitting | `leo/analysis/starlink/trajectories.py` | `fit_trajectory_bank` |
| Scan, fit and replay | `leo/analysis/starlink/trajectory_feedback.py` | `replay_pilot_trajectories` |
| Probe schedule | `leo/analysis/standard/probes.py` | `build_probe_schedule` |
| Stage analyzers | `leo/analysis/standard/analyzers.py` | `production_standard_v2_registry` |
| Report and status gates | `leo/analysis/standard/reports.py` | `build_path_standard_report` |
| DAG expansion | `leo/pipeline/topology.py` | `compile_standard_run_plan` |
| Worker execution | `leo/processing/service.py` | `ProcessingService.run_once` |
| Presentation projection | `leo/application/standard_presentation.py` | `CatalogStandardPresentationRepository` |
| PNG rendering | `leo/presentation/standard_png.py` | `render_full_standard_plot_png` |

The exploratory lane under `tools/` runs the same kernel outside the DAG and
goes further in three directions the pipeline has not absorbed:

- four alternative track linkers compared side by side per detector family —
  `explore_glrt64_tracks.py`, `explore_all_pilot_method_tracks.py`;
- an iterative tracklet EM diagnostic comparing quadratic and cubic Doppler
  models in a two-by-two panel with per-track BIC —
  `explore_iterative_tracklet_em.py`;
- cross-method seeding, where a GLRT-64 seed plus a robust residual corridor
  recovers a symbolwise tracklet the strict adjacent-point gate misses —
  `explore_anchor_symbolwise_recovery.py`,
  `compare_glrt_symbolwise_segmentation.py`.

The four-path shared-clock renderer `render_four_path_glrt64_feedback.py` aligns
all four receiver paths on the union of first-sample estimates, preserving the
measured start skew between the two radios.

## Reference recording

- session `production-24h-20260819-01-trial-00000132`;
- 60 seconds at 2.5 MS/s, two radios by two receivers, four paths;
- manifest digest
  `sha256:1712bf9293b684540824ad4adfe0764a3477d01d7da8fdb28398ae465076855d`;
- `stream-1` starts at estimated UTC ns `1787121029924226035`, `stream-0` starts
  1,425,210 ns later, union 60.001424810 s;
- manifest reports degraded best-effort synchronization and
  `phase_coherent=false`.
