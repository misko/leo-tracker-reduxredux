# V16 satellite localization from raw IQ to position

Implementation specification and experimental results. Prepared 5 October 2026,
America/Los_Angeles; artifact directory uses the execution host's 6 October UTC
date. Intended readers: signal-processing and numerical-software engineers
implementing an independent version of the model.

## Executive summary

V16 estimates a receiver's horizontal position from satellite pilot Doppler. Its
input measurements originate in recorded complex IQ, not in orbit predictions.
Each candidate is refined using the pilot waveform alone. The pipeline retains
one measurement per passing receiver/channel/20 ms window, calibrates shared
receiver frequency errors at the known reference location, and selects a compact
satellite set with greedy matching followed by removal and replacement. The
final position fit uses a soft satellite-or-clutter likelihood and Gaussian
timing penalties.

**V16 specifically names the final position-score configuration.** It does not
name a new GLRT detector or a new association solver. Its settings are a 125 Hz
frequency width, detection budget 1.6, clutter rate 0.5, common timing prior
standard deviation 3 s, and relative timing prior standard deviation 0.15 s.
This report specifies the entire upstream pipeline that produced its saved
N01–N16 results, not a hypothetical combination of later improvements.

Across these 16 independently fitted scans, the upstream fitted-`c` association
selects **42,610 of 46,775 passing windows, or 91.10%**. V16's median position
error is **1,167 m with fitted `c`** and **1,280 m with `c = 0`**, within a 4 km
search disk. All 16 fitted-`c` solutions meet the recorded stationarity criterion;
15 of 16 `c = 0` solutions do. These are **development results conditional on
known-roof calibration**, not blind localization accuracy or verified satellite
identity rates. High coverage and low frequency residuals do not establish an
accurate position.

The report includes an independent NumPy implementation of the final equations.
It reproduces the objectives of all 32 saved V16 solutions with maximum absolute
difference **8.01 × 10⁻¹¹**, and their posterior-weighted frequency RMS with
maximum difference **5.86 × 10⁻¹² Hz**. This checks the mathematical specification
at the saved states; it is not an independent IQ replay or a new optimization.

Companion material:

- [Readable HTML version](report.html), with online MathJax equation rendering.
- [Independent numerical reference](reference_math.py) and [tests](test_reference_math.py).
- [All numerical checks](numerical-check.json), [per-scan results](results.csv),
  [cohort identities and counts](cohort.csv), and [aggregate results](summary.json).
- [Pilot-state constants](pilot-states.json), needed to synthesize the templates.
- [Implementation source snapshots](implementation-sources.zip) and their
  [file-by-file provenance](implementation-sources.json). These are an algorithm
  reference appendix, not a packaged end-to-end application.
- [Input/result hashes](source-manifest.json) and [figure/report builder](build_report.py).

## 1 Scope and the complete computation

![End to end pipeline](figures/01-pipeline.png)

The computation has three distinct scores. Confusing them changes the algorithm:

| Stage | Quantity | What it chooses |
| --- | --- | --- |
| Pilot detection and refinement | Exact GLRT statistic minus control statistic | A frequency/epoch hypothesis from IQ |
| Discrete association | Assigned windows minus 10 times selected satellites | A compact set of satellite timing modes |
| V16 position refinement | Negative log likelihood plus Gaussian timing penalties | Position and continuous nuisance parameters |

The last stage does not maximize coverage. It does not rerun the greedy solver
at every location. It freezes the input windows and selected satellite bank, but
can redistribute probability among those satellites and clutter.

The saved experiment has the following boundaries:

- N01–N16 are separate 300 s scans at 2.5 million complex samples/s per receiver.
  They are not one jointly estimated trajectory or one combined position fit.
- Metadata establishes the same nominal fixture: RX0 points west, azimuth 270°;
  RX1 points east, azimuth 90°; each is tilted outward 20° from zenith, giving
  40° separation. V16 does **not** impose east/west exclusivity or a cone model.
- The orbit bank uses a snapshot collected before each scan, not the later-TLE
  backward-propagation experiment.
- The saved first candidate-guided IQ refinement is used. The later second-pass
  refinement study is not silently substituted.
- V16 uses the hard geometric horizon, not the subsequent smooth-horizon Q1
  model. It has no curvature-ratio filter, cone weights, ambiguity dropping,
  satellite-specific frequency drift, or temporal-density weights.
- Historical A/B results are not exact V16 runs. No matched V16 A/B result is
  claimed here.

The authoritative score settings are in
[position_score_sweep.py](../2026_10_04_t1_at_v1_replication/position_score_sweep.py).
The reported snapshot is its `position-score-sweep/polished` output, after the
matched convergence continuation, not its earlier `initial` or `final` directory.

## 2 Data records and units

Let `g` index a receiver/channel probe window, `j` a candidate within that window,
`s` a satellite, `r` a receiver, and `m` a pilot symbol. A probe means a particular
20 ms slice on one receiver and tuned channel. The simultaneous other receiver
has a different probe identity. Channels are revisited through retuning; the
scan is not 300 s of uninterrupted IQ at every channel.

| Field | Meaning and units |
| --- | --- |
| Session and capture hash | Bind all measurements to one immutable recording |
| Visit, receiver, probe index | Identify a source window within that recording |
| Candidate rank and candidate ID | Identify an acquisition hypothesis, not a new physical event |
| `time_s` | Original projected pilot-support center, seconds after capture origin |
| `rf_hz` | Actual RF reference for the visited pilot lane, in Hz |
| `original_hz`, `output_hz` | Saved and refined tracking CFO, in Hz |
| Integer epoch and fractional offset | Pilot-frame phase, in samples of the original IQ |
| Exact, control, margin | Dimensionless statistics; margin equals exact minus control |
| Source group | All candidate hypotheses from the same receiver/channel window |
| Original row index | Stable linkage through refinement, selection and positioning |

A group ID hashes capture digest, visit, receiver, and probe. A candidate ID
additionally binds rank and analysis digest. Never use an approximate time match
as a substitute for these identities. The source projection omits overlapping
probes in the same visit/receiver; the archived 120 ms probe stride makes these
20 ms windows nonoverlapping.

All Doppler calculations below use the **actual RF in Hz**. The geometric state
bank uses kilometres and kilometres/second; light speed is 299,792.458 km/s.
Receiver slopes use Hz/s. The calibration coefficient `c` uses Hz/GHz and is not
the speed of light. Use `c_light` for the latter in an implementation.

## 3 Reading IQ and recovering the observation time

### 3.1 Capture layout

Use the public recording adapter to read retained valid visits. A retained-visit
ordinal is not necessarily the event number: resolve the mapping through the
recording receipt. Verify the manifest and payload hashes before using a visit.
Exclude transition and invalid sample regions. Do not infer consecutive time
from concatenated payload locations across a retune.

The archived replay reads signed 16-bit I and Q with shape
`(sample, receiver, I_or_Q)`. For receiver `r`, convert to complex128:

\[
x_r[n]=(I_r[n]+iQ_r[n])/32768.
\]

For a 20 ms probe at 2.5 MS/s, use exactly 50,000 complex samples. The probe
starts at `probe_start_ms * sample_rate_hz // 1000` within the valid visit. The
offline products used here have a 120 ms probe stride. A 120 ms visit supplies
one probe per receiver; 240/360 ms visits can supply two/three. Passing activity
does not mean that every possible 20 ms interval in the raw recording was tested.

### 3.2 Frequency reference before acquisition

The pilot template is centered on the mean frequency of eight known pilot
subcarriers. The nominal pilot baseband frequency is

\[
f_{\rm nominal}=F_{\rm pilot}-F_{\rm LNB}-F_{\rm tuner,actual}.
\]

This is a hardware/tuning calculation, not a fitted satellite Doppler. The
installed acquisition code searches a residual relative to this center. The
tracking CFO returned by GLRT is in the IQ baseband convention. Preserve the
archived convention throughout; do not apply a nominal-center subtraction twice.
The later projection's actual RF is target RF minus the recorded IF offset.

### 3.3 Timestamp construction

Capture UTC is tied to a host-bracketed device-counter origin. Subtract integer
device counters **before** converting to float. If `C0` is the capture's first
device counter, `Cv` the valid visit start, `np` the probe offset and `nc` the
pilot-support center within the probe, then

\[
t_g=(C_v-C_0+n_p+n_c)/F_s.
\]

The support center is the mean of the valid GLRT symbol-segment centers across
supported frames, not simply `probe_start + 10 ms`. Fractional interpolation
guards participate in support validity. The source projection also stores
support endpoints and moments. The position model evaluates instantaneous
Doppler at the center; it does not integrate Doppler against those moments.

In this V16 input lineage, candidate-guided refinement changes CFO and ranking
but **retains the original projected `time_s`**. Its new fractional epoch is not
used to regenerate a new timestamp. This detail is necessary for exact replay.

For N01, the first RX0 candidate has `time_s = 0.128361420`, with projected
support from 0.118884400 to 0.137838800 s. Its capture UTC bracket is about
366.620 ms wide. That is timing evidence, not an assertion of nanosecond timing
accuracy because the timestamp is stored in nanoseconds.

## 4 Pilot waveform and initial acquisition

### 4.1 Exact and control templates

The pilot construction uses a 750 Hz frame repetition rate, symbol duration
4.4 μs, cyclic prefix duration 0.133333… μs, and subcarrier spacing 234,375 Hz.
At 2.5 MS/s one symbol spans 11 samples. The physical frame period is
3,333⅓ samples; a sampled template contains `round(Fs/750) = 3333` samples.
These two quantities are deliberately different.

The lower-edge subcarrier indices are 528…535; the upper-edge indices are
488…495. The 16 hexadecimal integers in [pilot-states.json](pilot-states.json)
each encode 300 two-bit pilot states. For row `j = 0…299`, subcarrier `k`, and
control roll `u`, decode

\[
b_{jk}=\big(H_k\gg[2(299-((j-u)\bmod300))]\big)\mathbin{\&}3,
\qquad q_{jk}=e^{i\pi(b_{jk}+1/2)/2}.
\]

Use `u = 0` for the exact template and `u = 17` for the control. Interpret
subcarrier indices at or above 512 as `k−1024`, multiply by 234,375 Hz, then
subtract the mean of the chosen eight frequencies to obtain offsets `f_k`.
For a sample at time `t`, let `m = floor(t/Tsym)` and
`tlocal = t − m Tsym`. The frame template is zero outside symbols 2…301 and,
within those symbols, is

\[
p(t)=\frac1{\sqrt8}\sum_{k=1}^{8}q_{m-2,k}
       e^{2\pi i f_k(t_{\rm local}-T_{\rm CP})}.
\]

The archived template is stored as complex64, then cast to complex128 during
correlation. Match this rounding if reproducing the last bits. The constants
are the locally archived factual pilot states; the source appendix contains
their exact construction and attribution.

### 4.2 Search a bounded frequency and epoch grid

Initial acquisition supplies plausible starting basins, not satellite identities.
It does not know an orbit. The adaptive scanner's frequency search range is
limited by the entire eight-tone template fitting inside the recorded bandwidth:

\[
H=\min\left(800000,
f_{\rm nominal}+\min_k f_k+\tfrac12\min(F_s,B),
\tfrac12\min(F_s,B)-f_{\rm nominal}-\max_k f_k\right).
\]

Search residual CFO from `−H` to `+H`, then add `fnominal`. At zero nominal
offset and 2.5 MHz sample rate/bandwidth, the eight-tone offsets span
±820,312.5 Hz, so **H = 429,687.5 Hz**. Do not copy the generic acquisition
default of ±400 kHz: the adaptive caller overrides it with this capture geometry.

The historical scanner settings are:

| Operation | Setting |
| --- | --- |
| Coarse CFO grid | 80,000 Hz spacing, including a final endpoint if needed |
| Initial anchor symbols | `range(2,302,26)` |
| Epoch candidates | Integer frame phase 0…3332 |
| Retained acquisition basins | At most 8 per probe |
| Basin suppression | Reject a new peak when circular epoch distance <5 samples **and** CFO separation ≤10,000 Hz from a retained one |
| Fine CFO sweep | ±80,000 Hz around coarse CFO, 500 Hz spacing, clipped to search support |
| Fine symbols | Even symbols 2…300 |
| Conditioned sweep | ±2,000 Hz around interpolated fine peak, 100 Hz spacing |
| Verification symbols | Odd symbols 3…301 |
| Minimum verification support | 2 frames |
| Conditional fallback | Repeat a receiver lacking a fractional detection with `range(2,302,14)` anchors if the other receiver has one |

For each coarse CFO, derotate IQ and compute normalized absolute correlation
against each short anchor-symbol template for every feasible integer epoch and
frame. Average supported anchor/frame contributions. Retain local maxima, sort
by score with deterministic CFO/epoch tie breaks, and apply the suppression rule.
Refine an epoch by choosing its best valid immediate integer neighbor.

For a set of sample indices `S` within a frame, the fine score is the mean across
supported frames of

\[
\frac{\left|\sum_{n\in S}\overline{p[n]}x[n+n_f]
                    e^{-2\pi i f n/F_s}\right|}
{\sqrt{\left(\sum_{n\in S}|p[n]|^2\right)
              \left(\sum_{n\in S}|x[n+n_f]|^2\right)}}.
\]

Interpolate the fine CFO peak with the ordinary three-point quadratic, bounded
to one grid step; use the grid peak at an edge or nonconcave fit. The conditioned
sweep uses the complete frame template. Rank acquired basins by verification
exact-minus-control margin, then the other recorded scores and deterministic
CFO/epoch ties. This ranking precedes the GLRT refinement below.

The even/odd pilot split is an **intra-window acquisition diagnostic**. It is not
a train/test split of localization windows. The eventual GLRT uses symbols
2…65, containing both even and odd symbols.

## 5 The GLRT frequency estimate

![GLRT structure and a real refinement example](figures/02-glrt-refinement.png)

### 5.1 Condition the pilot correlations

For an acquired center frequency `fa` and frame epoch `e`, frame `l` starts at
`e + round(l Fs/750)`. Correlate symbols `m = 2…65` individually after derotating
the IQ by `fa`. With fractional epoch `ε`, sample the IQ continuously using the
interpolator in the next section. Denote each resulting complex correlation by
`z[l,m]`. Use only the initial sequence of frames for which all 64 selected
symbols are valid. Correlations are complex sums, **not** their normalized
per-symbol power diagnostics.

For residual frequency `r`, calculate

\[
P(r)=\sum_l\left|\sum_{m=0}^{63}z_{lm}e^{-2\pi i r mT_{\rm sym}}\right|^2,
\qquad C=\sum_l\left(\sum_m|z_{lm}|\right)^2.
\]

The exact GLRT statistic is `max_r P(r)/C`. Calculate the control statistic by
the same procedure with the roll-17 template, maximizing it independently and
using its own normalization. The candidate's margin is

\[
M=G_{\rm exact}-G_{\rm control}.
\]

The winning exact residual supplies the tracking CFO:

\[
f_{\rm tracking}=f_a+r_{\rm exact}.
\]

A control peak does not supply the frequency. A margin is a detection/ranking
statistic, not a calibrated probability of signal presence or correct NORAD ID.

### 5.2 Aliasing and the finite grid

The residual grid is `fftfreq(4096, d=4.4e-6)`. Its spacing is approximately
55.4865 Hz, and its period is

\[
A=1/T_{\rm sym}=227272.7272727\ldots\ {m Hz}.
\]

Only the symbol-to-symbol phase progression determines this residual frequency.
Frequencies separated by `A` have identical phase progression at the symbol
centers. This is distinct from the 2.5 MHz IQ sample-rate alias period. The
within-symbol conditioning and template-band shape can distinguish neighboring
acquisition branches, which is why recentering and rescoring the actual IQ can
improve a candidate.

Use the half-open circular residual consistently:

\[
\operatorname{wrap}_A(u)=((u+A/2)\bmod A)-A/2.
\]

Zero-padding 64 correlations to 4096 samples interpolates a frequency search
grid; it does not create 4096 independent pilot symbols. Coherent integration
is across 64 symbols in a frame. Powers, not complex frame amplitudes, are
summed across frames. It is not a coherent 20 ms frequency estimator.

The direct FFT expression above is a reimplementation oracle. The archived
code can instead sum short autocorrelations and transform the padded result;
both compute the same spectrum. Handle a zero ceiling without division by zero.

### 5.3 Initial fractional epoch and passing gate

At fixed acquired CFO, score integer epoch offsets `−2,−1,0,+1,+2` on the
circular 3333-sample frame-phase domain. Around an interior peak with positive
scores, fit a parabola to their logarithms. For equally spaced cells,

\[
d=\operatorname{clip}\left(
\frac{\log G_{-}-\log G_{+}}
 {2(\log G_{-}-2\log G_0+\log G_{+})},-0.5,0.5\right).
\]

Require a finite concave peak; otherwise retain the appropriate non-refined
status. Evaluate the proposed fractional epoch against IQ, rather than merely
interpolating the score. The interpolation uses 16 Lanczos taps: for continuous
sample `t`, take integer indices `floor(t)+[-7,…,8]` and weights proportional to
`sinc(t−j) sinc((t−j)/8)`, normalized to sum to one. Exact integer positions use
the exact sample. Fractional positions require seven left and eight right guard
samples; do not wrap raw IQ across the probe boundary.

The scanner's passing criterion is fractional exact-minus-control margin
**at least 0.025**. Only those original passing hypotheses enter this research
inventory. A later plot at threshold zero would therefore not reconstruct all
failed original acquisition hypotheses. The report does not treat such a plot
as a new zero-threshold detector run.

## 6 Orbit free candidate refinement and top one selection

### 6.1 Three bounded rescoring passes

Start every original passing candidate independently, using its own saved
tracking CFO and fractional frame epoch. No TLE, known roof, neighboring track,
satellite prediction, or orbit residual enters this refinement.

```text
f = original tracking CFO
e = original integer epoch + original fractional offset
best = none
for pass in [1, 2, 3]:
    pass 1: centers = [f-A, f, f+A]; epoch offsets = [0]
    pass 2: centers = [f]; epoch offsets = [-.5, -.25, 0, .25, .5]
    pass 3: centers = [f]; epoch offsets = [-.25, -.125, 0, .125, .25]
    score every center and epoch with the actual conditioned GLRT
    discard nonfinite outputs
    discard |wrap(tracking_CFO - tested_center)| > 1000 Hz
    include best from the preceding pass, if there is one
    choose the highest exact-minus-control margin, stable first tie
    f = chosen tracking_CFO; e = chosen tested epoch
return best, trace, status, original candidate identity
```

This is 3 + 5 + 5 = **13 GLRT calls per candidate** in a complete three-pass
run. The center check is a local-refinement guard, not an orbit residual gate.
The first pass does not include the original saved score as a protected incumbent;
subsequent passes retain their previous best. Thus margin is nondecreasing
between successful refinement passes, but is not guaranteed nondecreasing
relative to the original scanner statistic. If no local maximum survives,
retain the original candidate frequency and score with an explicit failure flag.

No records are merged during refinement. Similar candidates can converge to
nearly the same frequency, and a distant candidate can represent another signal.
Frequency proximity alone is not a physical-identity test.

### 6.2 Worked recorded example

N01, first visit, RX0, candidate rank 0:

| Stage | Tracking CFO Hz | Tested epoch samples | Margin |
| --- | ---: | ---: | ---: |
| Original fractional result | −209,196.772832 | 484.716956 | 0.425914 |
| Refinement pass 1 | −209,085.799820 | 484.716956 | 0.427089 |
| Refinement pass 2 | −209,085.799820 | 484.966956 | 0.429438 |
| Refinement pass 3 | −209,085.799820 | 484.841956 | 0.432656 |

The frequency changed by +110.973011 Hz. Pass 1's new center is the original
tracking CFO, not a random guess and not a satellite frequency. The two later
passes improve the epoch and score even though the winning frequency bin is
unchanged. Across N01–N16, 134,781 of 134,835 candidate refinements succeeded;
54 retained original values. All input candidate identities remain accounted for.

### 6.3 Choose exactly one candidate per source window

![Actual candidates before and after refinement](figures/03-top-one.png)

For each source group choose `argmax(refined_margin, −original_row_index)`.
The second key makes ties deterministic. For failed refinements use the original
margin. This yields 46,775 retained windows from 134,835 passing hypotheses.
There is no new 0.2 or 0.6 score cut in this pipeline. The strongest candidate is
chosen by margin, not by closest orbit, largest absolute CFO, acquisition rank,
or exact statistic alone.

Top-one is a deliberate simplification. Multiple satellites may emit in one
20 ms receiver/channel window, but V16 retains only one representative
measurement from it. Satellites can still be active simultaneously across
different receiver/channel windows. Discarded alternatives are neither extra
unexplained windows nor modeled simultaneous detections in the final objective.

## 7 Orbit bank and Doppler prediction

### 7.1 Catalogue and frame transformation

For each scan choose the latest archived TLE snapshot **collected strictly before
the capture origin**. Snapshot collection time and the element's orbit epoch
are different fields. Validate TLE checksums and catalogue-number consistency,
remove labelled Starlink debris, and report propagation failures rather than
silently converting them into plausible tracks.

Propagate candidates with SGP4 at 0.25 s nodes from −21 s through the rounded-up
scan end plus 21 s. Use split Julian day/fraction inputs. Reject candidates with
any SGP4 error, nonfinite state, or geocentric radius at most 6498.137 km. Rotate
TEME states into the rotating ECEF frame:

\[
p_E=R_z(-\theta_{\rm GMST})p_T,\qquad
v_E=R_z(-\theta_{\rm GMST})v_T-\omega\times p_E.
\]

The Earth-rotation velocity term is essential: the receiver is stationary in
ECEF, not inertial space. The implementation uses
`ω = 7.292115146706979e−5 rad/s`, UTC as the approximation to UT1, and no polar
motion. GMST is the IAU-1982 polynomial reproduced in `sky/frames.py` in the
source appendix. These are model approximations, not fitted parameters.

Keep a candidate in the cached bank if it reaches elevation ≥−1° at the known
roof anywhere on the expanded time grid. This is a generous cache-retrieval
condition. The actual observation likelihood and association use elevation ≥0°
at the queried time and location. N01, for example, retains 926 candidates from
a catalogue of 11,129 after these checks. There is no final 10- or 11-satellite
shortlist imposed on discovery.

### 7.2 Receiver and satellite geometry

The reference location is latitude 37.849056280893684°, longitude
−122.48575489722863°. This benchmark holds altitude at **0 m WGS84 ellipsoidal
height**, even though the reference is called the roof. Height is not estimated.
Convert candidate latitude/longitude to WGS84 ECEF with semimajor axis
6378.137 km and flattening `1/298.257223563`.

At shifted time `t_g + u_s`, linearly interpolate **position and velocity
independently** between adjacent bank nodes. For receiver ECEF position `x_E`,

\[
\rho=p_s-x_E,\quad d=\|\rho\|,\quad \ell=\rho/d,\quad
\dot d=\ell^Tv_s,\qquad
D_s(x,t;F_g)=-\frac{F_g}{c_{\rm light}}\dot d.
\]

An approaching satellite has negative range rate and positive Doppler. Visibility
is `ℓ · up(x) ≥ 0`, where `up` is the local geodetic normal. Both receivers share
this geometric observer position. V16 does not use receiver antenna direction
to make a satellite visible on one receiver and invisible on the other.

Use actual receive time for receiver drift; shift only the orbit query. The
±20 s satellite timing parameter is a flexible orbit-alignment parameter, not a
claim that the recording clock is wrong by 20 s or a fitted physical light-time
delay. There is no separate transmit-time/light-travel correction in this model.

## 8 Initial tracks and full data receiver calibration

### 8.1 TLE blind track seeds

Calibration needs initial receiver offsets, drifts and approximate orbit matches.
Construct tracklets from positive-margin top-one observations without a TLE:

1. Partition by receiver, channel, edge and actual RF. Normalize CFO and its
   alias spacing to a common 11.2 GHz reference by multiplying by `11.2e9/Fg`.
2. Use an alias-aware weighted Hough line search, slopes −15,000…+15,000 Hz/s
   on 3601 bins, 512 intercept bins, and 64 candidate peaks. The residual gate
   is 2500 Hz, maximum time gap 4 s, minimum support 8, minimum span 4 s,
   minimum point weight 0.1, and at most 8 tracks per lane.
3. Refine supported line segments and enforce one hypothesis per source group.
   The exact Hough weighting, refinement and deterministic tie rules are in
   `analysis/cfo_lines.py` in the source appendix.
4. For the calibration bootstrap, retain tracks with at least 15 observations
   spanning at least 15 s. Choose up to the 12 longest tracks per receiver.

Only these bootstrap seeds have this small-track limit. Exhaustive association
later searches the whole near-visible bank. The episode graph's optional
cross-lane linking is not required to choose these lane tracklets.

### 8.2 Match track shapes to initialize nuisance parameters

For each seed, unwrap its CFO modulo `A`, test every bank satellite at time
offsets −20,−18,…,+20 s, and fit a free constant to the observed-minus-orbit
sequence. The constant is only an initializer; it is not a permanent
satellite-specific frequency parameter. Use the robust loss

\[
\rho_{200}(e)=2(200)^2\left(\sqrt{1+(e/200)^2}-1\right).
\]

Initialize the constant at the median and perform up to 20 iteratively weighted
location updates with weights `1/sqrt(1+(e/200)²)`, stopping at <0.01 Hz change.
Rank by mean robust loss, then absolute timing shift and catalogue ID. Require
at least 90% geometric visibility and shape RMS below 2000 Hz. Keep the five
best alternatives in the receipt. Require accepted seeds on both receivers.

To initialize each receiver line, use wrapped residuals of its accepted seeds.
Try the centers of the three most-populated bins of a 128-bin histogram on
`[−A/2,A/2)`, with slope starts −20, 0, +20 Hz/s. Fit offset and slope using
soft-L1 least squares, a ±50 Hz/s slope bound, and up to 80 evaluations per
start. Each point in a seed of length `n` receives weight `sqrt(min(n,100))/n`;
the normalized least-squares residual is `sqrt(weight)*wrapped_error/200`.
This track-balancing applies to initialization, not the final V16 likelihood.

Try common timing starts −10,−5,0,+5,+10 s. The `seed-timing-v6` initialization
also preserves shape-derived per-satellite timing: take the observation-count
weighted median of each satellite's track offsets, subtract the mean across
seed satellites, add each common start, and clip total shifts just inside ±20 s.
Retain both the zero-relative and shape-relative timing families, ten starts
in all. Score starts by the mean of the accepted tracks' mean robust losses.

### 8.3 Fit the receiver model at the known roof

At this stage the receiver location is fixed at the reference roof. Use **all
passing top-one windows**, including windows not in the bootstrap tracks, with
the bootstrap satellite bank and a soft satellite/clutter likelihood. The
calibration model is

\[
\mu_{gs}=D_s(x_{\rm roof},t_g+\tau+\delta_s;F_g)
 +a_{r_g}+b_{r_g}(t_g-150)+c(F_g-F_{\rm ref})/10^9.
\]

Use `Fref = mean(unique(actual RF values))`, not an observation-weighted RF
mean. N01 uses 11,315,312,499 Hz. Calibration uses the original settings
`σf = 200 Hz`, `D = 0.8`, `λ = 2`, `στ = 10 s`, `σδ = 1 s`, with the timing
gauge and bounds described below. **Do not apply V16's tighter settings at this
upstream stage when reproducing these results.**

The exact saved lineage is `full-scan-seed-restart`. Its prefit compares the
previous full-data prefit and the best archived nuisance initialization, gives
both a 15 s full-window optimization, and polishes the lowest objective for
20 s. Archived fold fits can supply starting values, but every evaluated
candidate is repriced and optimized on the same complete window set. There is
no held-out fold in this calibration. The improved prefit must meet the
fixed-location nuisance stationarity criterion before proceeding.

### 8.4 Fit a small nonlinear receiver correction

![Actual receiver calibration](figures/04-calibration.png)

Use the fitted-`c` prefit to identify spline-training support. Retain a window's
highest-responsibility satellite only when responsibility ≥0.8, elevation ≥0°,
and absolute wrapped residual ≤600 Hz. This is a **quality-selected subset**,
not a held-out evaluation split. N01 has 1,919 such windows out of 2,728 passing
windows.

The correction called a spline is piecewise linear on 11 knots
`0,30,…,300 s`. For each receiver let `B(t)` be the linear-interpolation basis
on these knots. Let `N` be an 11-by-9 orthonormal null basis of the two knot-grid
vectors `1` and `(t−150)/150`. Write correction `s_r(t)=B(t)Nβ_r`. This prevents
the nonlinear correction from duplicating the receiver constant and line on
the knot grid. It does not guarantee zero mean at irregular observation times.

Let `D2` take second differences across knots. Solve separately for each RX:

\[
\beta_r=(X^TWX+P)^{-1}X^TW e,\qquad X=B N,
\quad P=I/50^2+(D_2N)^T(D_2N)/25^2.
\]

Start `W = I/200²`. Perform three solve/update iterations; after each solve,
set each weight to `min(1,200/max(|e−Xβ|,1e−9))/200²`. Keep the third solve's
coefficients. The priors constrain correction amplitude and roughness in Hz.
There are nine nonlinear coefficients per receiver, 18 in total. This is
shared across channels; there is no independent spline per satellite or channel.

Subtract this correction and refit the full-window receiver/timing/RF model.
Use improved-prefit and previous-postfit starts, 15 s each, then a 20 s polish.
Fit both RF arms with the same correction learned from the fitted-`c` prefit.
The frozen baseline for the downstream positioning experiment is the fitted-`c`
postfit's RX lines plus that nonlinear correction:

\[
h_r(t)=a_r^{\rm cal}+b_r^{\rm cal}(t-150)+s_r(t).
\]

This baseline excludes the RF coefficient term. Later position refinement fits
additional receiver lines, not a new nonlinear spline. Both final-position RF
arms share this same frozen baseline, so `c = 0` is a controlled **final-score
ablation**, not an end-to-end removal of RF-dependent calibration history.

## 9 Discover satellite timing modes across the visible bank

Hold the roof and fitted calibration fixed. For each satellite, test **absolute
orbit shifts** from −20 to +20 s at 1 s coarse spacing. This full-data adapter
does not add the old calibration common timing to the tested offset. Avoid
copying the historical fold adapter's common-relative interpretation.

At coarse shift `u`, calculate wrapped residual `e` and orbit timing derivative
`d = ∂D/∂u`. Form a continuous root proposal

\[
u_{\rm proposal}=u+e/d.
\]

Accept a vote only if the satellite is visible, `|d| > 1 Hz/s`,
`|e| ≤ 0.75 |d| + 600 Hz`, and `|uproposal| ≤20 s`. The permissive coarse
envelope is a retrieval condition; a coarse grid point need not itself fall
within the final 600 Hz association gate.

Round timing votes to 0.05 s bins. In each bin, count unique source windows
within ±0.10 s, not repeated votes from the same window at different coarse
times. Extract the strongest mode with at least 10 unique windows, set its
timing to the median nearby continuous vote, suppress bins within ±0.20 s,
and repeat until no supported mode remains. Ties use increasing bin order.

For each proposed mode, perform three timing-only refinements. On visible
windows within ±600 Hz, take the closest currently considered hypothesis per
window and update

\[
\Delta u=\frac{\sum_g d_g e_g/200^2-u}{\sum_g d_g^2/200^2+1},
\qquad u\leftarrow\operatorname{clip}_{[-20,20]}
 (u+\operatorname{clip}_{[-0.1,0.1]}\Delta u).
\]

The `−u` and `+1` encode the discovery proxy's 1 s zero-centered timing penalty;
they are not V16's final relative timing prior. Stop refining a mode if fewer
than 10 eligible windows remain. Generate modes in both calibration RF arms,
take the union of identical `(satellite, timing)` hypotheses, and evaluate that
same union under both calibrations. Distinct close floating-point mode values
are not automatically consolidated in the archived pool.

For each mode save all visible rows within ±600 Hz and their signed residuals.
This cached incidence structure is what makes repeated greedy and replacement
trials inexpensive. It also makes the search finite: it cannot discover an
unproposed continuous timing basin during a replacement trial.

## 10 Greedy matching and satellite replacement

![Association coverage and algorithm](figures/05-association.png)

### 10.1 Coherent support and exclusivity

Evaluate each mode against currently free windows. Partition its support into
receiver/channel lanes, select the closest eligible row per source window,
order by receive time, and split whenever consecutive times differ by more than
5 s. Retain only segments with at least 10 windows spanning at least 5 s.
Recompute these segments when claimed windows are removed from a mode's support.

There is one chosen timing mode per NORAD ID and one owner per retained window.
Different satellites can own different simultaneous windows. The top-one input
policy has already removed competition among multiple raw candidates inside
one receiver/channel window; it should not be described as recovering all IQ
signals in that window.

### 10.2 Greedy objective and tie breaks

Maximize

\[
S=N_{\rm assigned\ windows}-10N_{\rm selected\ satellites}.
\]

Starting with no chosen satellites, add the available mode with the most
currently free coherent windows, but only when that count exceeds 10. A mode
with exactly 10 contributes zero score improvement and is not added. Break
count ties with

\[
T=-\frac12\sum e_g^2/200^2-\frac12u^2,
\]

then smaller NORAD ID, then smaller mode index. `T` is only a tie-breaking
proxy; the primary objective is not weighted RMS or GLRT margin. Claim the
winner's windows and recompute modes sharing those windows. Already selected
satellites keep their existing memberships during this greedy fill.

### 10.3 One out and greedy many in

```text
chosen = greedy_fill(empty set)
for pass in 1..3:
    accepted = 0
    for satellite in snapshot_of_current_chosen_order:
        trial = chosen without satellite
        release only that satellite's windows
        temporarily forbid the removed NORAD ID
        greedily fill trial with unchosen modes, recomputing free coherence
        if score(trial) > score(chosen):
            allow removed NORAD ID again
            greedily fill once more if any remaining mode pays its penalty
            chosen = trial
            accepted += 1
    if accepted == 0: stop with no-improvement status
```

Unchanged satellites' memberships and receiver calibration remain fixed within
a trial. The procedure can replace one satellite by several, and can reduce
satellite count while improving the penalized score. It is not an exhaustive
set-cover solution, arbitrary multi-out search, or joint nuisance refit.
A completed no-improvement pass establishes only a fixed point for this
particular repair neighborhood. Reaching three passes while still improving
is a pass-limit termination, not convergence.

In the frozen fitted-`c` N-cohort inputs, greedy alone assigned 42,583 windows.
Replacement adds a net 27: 16 in N04 and 11 in N15, for 42,610 final windows.
For other scans it can still test alternatives without accepting a change.

## 11 Freeze the position input population

Take all windows assigned by the fitted-`c` association run, sorted by original
row ID, and the union of its selected NORAD IDs. Keep original owners as a
diagnostic label. Preserve time, actual RF, receiver, channel, refined CFO,
source identity, margin, and the selected satellites' ephemerides. Subtract
`h_rx(t)` from the refined CFO to obtain the position-fit measurement `y_g`.

Both final RF arms use exactly these observations and this satellite set, even
though a separate upstream `c = 0` association run exists. The `c = 0` final
position arm does not switch to that different membership set.

The final likelihood sees **every selected satellite at every retained window**,
not only the original owner's track interval. The horizon decides geometric
visibility. Thus a GLRT window can have fractional responsibility for more than
one selected satellite. This is uncertainty over its identity, not duplicating
the observation in a least-squares sum. A satellite discarded by greedy
selection is absent from this competition.

Unassigned passing windows and completely nonpassing probes are not in the
position objective. They remain important diagnostics but are not fitted as
clutter here. The likelihood's nonempty conditioning does not model all the
effects of top-one selection, original margin censoring, and association
selection. Consequently its responsibilities are model scores, not independently
calibrated identity probabilities.

## 12 V16 position model and all final hyperparameters

### 12.1 Prediction and timing gauge

After subtracting the frozen receiver baseline, predict

\[
\mu_{gs}=D_s(x,t_g+\tau+\delta_s;F_g)
 +a_{r_g}+b_{r_g}(t_g-150)
 +c\frac{F_g-F_{\rm ref}}{10^9}.
\]

`a` and `b` here are **additional** receiver corrections. `τ` is a common orbit
shift, and `δs` is a satellite-relative shift shared across all receivers and
channels. Each candidate satellite for a given GLRT therefore uses its own
`τ+δs`; timing is not a new free parameter for each individual measurement.

Impose `Σδs = 0` to remove the common/relative timing degeneracy. For `K`
satellites use a `K × (K−1)` orthonormal basis `B`, and write `δ = Bz`.
One deterministic construction for zero-based column `j` is:

```text
B[0:j+1, j] = 1 / sqrt((j+1)*(j+2))
B[j+1, j]  = -(j+1) / sqrt((j+1)*(j+2))
all other entries = 0
```

Then `BᵀB=I`, `1ᵀB=0`, and `||δ||²=||z||²`. The total timing vector has `K`
degrees of freedom: one common coordinate and `K−1` relative coordinates.

| Final setting | V16 | Matched C1 control |
| --- | ---: | ---: |
| Wrapped frequency standard deviation | 125 Hz | 200 Hz |
| Detection budget D | 1.6 | 0.8 |
| Poisson clutter rate λ | 0.5 | 2 |
| Common timing prior sigma | 3 s | 10 s |
| Relative timing prior sigma | 0.15 s | 1/3 s |
| Common timing hard bound | ±10 s | Same |
| Total timing τ+δs hard bound | ±20 s, inside bank support | Same |
| Extra receiver slope bounds | ±50 Hz/s for each RX | Same |
| Extra receiver intercept bounds | Unbounded | Same |
| RF coefficient bound when fitted | ±5000 Hz/GHz | Same |
| RF coefficient in control arm | Exactly 0 | Same |
| Position support | 4 km horizontal disk about roof | Same |
| Altitude | Fixed 0 m WGS84 | Same |
| Visibility | Hard elevation ≥0° | Same |
| Window weights | All 1 | Same |
| Noise width learned from residuals | No | No |
| Gaussian prior on a, b, or c | None | None |

There are `K+7` independent continuous parameters with fitted `c`, or `K+6`
with `c = 0`. This count excludes the earlier spline coefficients and discrete
satellite selection. V16 has the same fitted dimension as C1; it changes
hyperparameters, not model structure.

The RF coefficient is learned because the residual RF dependence is not assumed
to be completely known from tuning metadata. Its value cannot be interpreted
as one identified hardware clock error without additional evidence. Satellite
Doppler already scales with `Fg`; the `c` term is an extra shared RF-dependent
calibration correction, not a substitute for that physical scaling.

### 12.2 Single window finite set likelihood

![Likelihood and prior illustrations](figures/06-likelihood.png)

The underlying finite-set model allows each visible satellite to produce at
most one observation in a window, with independent Bernoulli detection, plus
Poisson clutter uniform over an alias interval. V16 has one retained observation
per window, so the general multi-peak dynamic program simplifies exactly to
the following scalar expression.

Define visibility `vgs ∈ {0,1}`, detection probability and empty-set probability:

\[
q_{gs}=\frac{D}{K}v_{gs},\qquad
P_{0g}=e^{-\lambda}\prod_s(1-q_{gs}).
\]

`D = 1.6` is a detection-count budget, **not a probability of 1.6**. Every
`qgs` must be below 1; the saved satellite banks satisfy this. The denominator
`K` is the size of the selected bank, not just the number visible in that window.

The wrapped Gaussian frequency density is

\[
\phi_A(e;\sigma)=\sum_{k\in\mathbb Z}
 \frac1{\sqrt{2\pi}\sigma}
 \exp\left[-\frac{(\operatorname{wrap}_A(e)+kA)^2}{2\sigma^2}\right].
\]

Let `ogs = qgs/(1−qgs)` and define

\[
H_g=\frac\lambda A+\sum_s o_{gs}\phi_A(y_g-\mu_{gs};\sigma_f).
\]

The density conditional on a nonempty observed set is

\[
\boxed{L_g=\frac{P_{0g}}{1-P_{0g}}H_g.}
\]

To derive it, the all-missed/no-clutter probability contributes `P0`. Exactly
one clutter observation contributes `λ/A`; assigning the observation to
satellite `s` replaces its miss probability by a detection, producing the odds
factor `qs/(1−qs)`. Divide by `1−P0` because persisted groups are nonempty.
Do not drop this normalization when visibility or satellite count changes.

For stable implementation compute `log P0 = −λ + Σlog1p(−q)`, and
`log(1−P0) = log(−expm1(log P0))`. Accumulate `H` with log-sum-exp. The archived
wrapped-normal evaluator includes image offsets through a 10⁻¹⁵ tail criterion;
at 125 Hz the nearest image dominates except at the wrap seam, where density
is already negligible compared with clutter.

### 12.3 Responsibilities and minimized loss

The responsibility for satellite `s` and the clutter probability are

\[
z_{gs}=\frac{o_{gs}\phi_A(y_g-\mu_{gs};\sigma_f)}{H_g},\qquad
z_{gC}=\frac{\lambda/A}{H_g}.
\]

They sum to one for each window. Two equally good satellite explanations split
responsibility; they do not each receive the full measurement weight. This
model does not impose an additional penalty specifically for ambiguity. The
`λ` here is a clutter-rate hyperparameter, not a penalty on coefficient `c`.

The minimized V16 objective is

\[
\boxed{J(x,a,b,c,\tau,z)=-\sum_g\log L_g
 +\frac12(\tau/3)^2+\frac12\sum_s(\delta_s/0.15)^2,\quad\delta=Bz.}
\]

Gaussian normalization constants for the fixed timing priors are omitted from
the optimized score. They do not affect a minimum within one configuration.
Raw penalized scores across different prior widths or likelihood settings are
not model-evidence comparisons.

There is no HMM transition probability in this final objective. Windows factor
conditionally on the shared parameters. Temporal coherence was used during
discrete selection, while orbit shape and common calibration link the windows
during positioning.

## 13 Gradient and constrained position refinement

### 13.1 Differentiate the same loss that is scored

Let `egs = wrap(yg−μgs)`. Away from a hard-horizon switch, `q` and the nonempty
normalization are locally constant with respect to continuous parameters.
For a narrow wrapped Gaussian,

\[
\frac{\partial J_{\rm data}}{\partial\mu_{gs}}
 \simeq-\frac{z_{gs}e_{gs}}{\sigma_f^2}.
\]

The exact implementation substitutes the image-probability-weighted mean of
`egs+kA` for `egs`. Multiply this prediction gradient by the Doppler and nuisance
Jacobians, then add prior gradients `τ/9` and `Bᵀδ/0.15²`.

The useful geometric derivatives can be implemented without differentiating
SGP4 on every iteration. For observer ECEF position,

\[
\frac{\partial D}{\partial x_E}
 =\frac{F_g}{c_{\rm light}d}\big(v_s-\ell\dot d\big).
\]

For timing, with interpolated position rate `p′` and velocity rate `v′`,

\[
\ell'=\frac{p'-\ell(\ell^Tp')}{d},\qquad
\frac{\partial D}{\partial u_s}
 =-\frac{F_g}{c_{\rm light}}(\ell'^Tv_s+\ell^Tv').
\]

Use `(p_upper−p_lower)/0.25` and `(v_upper−v_lower)/0.25` as those rates to
differentiate the **actual interpolated model**. Do not substitute velocity for
the derivative of linearly interpolated position and then claim an exact
gradient. Receiver derivatives are 1 and `tg−150`; the RF derivative is
`(Fg−Fref)/1e9`. Common timing sums satellite timing derivatives; relative timing
multiplies them by the zero-sum basis.

The source implementation estimates the observer-coordinate transform's
Jacobian with central 1 m perturbations. Ephemeris knots and the hard horizon
make the model piecewise smooth. A horizon crossing can introduce a jump;
V16 does not differentiate that indicator as if it were smooth.

### 13.2 Position coordinates and hard constraints

Optimize east/north offsets in kilometres within `E²+N² ≤16`. Convert these to
geodetic position by a spherical direct geodesic from the roof, with radius
6371.0088 km, bearing `atan2(E,N)`, and arc length `hypot(E,N)`. Then use WGS84
ECEF for the observation geometry.

Historical `parameters[:2]` are stored in a different spherical coordinate
chart centered at latitude 38.5816°, longitude −121.4944°. They are **not** the
roof-relative east/north coordinates. The result field `best.point_km` is the
roof-relative coordinate used for plots and error. An independent implementation
may avoid the historical intermediate chart, provided the final physical
observer position and derivatives agree. The companion reference handles the
saved chart exactly.

Parameter scaling in optimization is 1 km for the two external position
coordinates, 1000 Hz for receiver offsets, 10 Hz/s for slopes, 1 s for timing
coordinates, and 1000 Hz/GHz for `c`. The total satellite timing constraints
are linear in `[τ,z]`: `−20 < τ+Bz <20`, with a 1 μs numerical interior margin
and additional ephemeris support checks. Apply the separate common ±10 s bound
as well. A 0.15 s Gaussian prior is **not** a ±0.15 s hard bound.

### 13.3 Fisher steps and line search

A positive local curvature approximation uses responsibilities as weights:

\[
H\approx\sum_{g,s}\frac{z_{gs}}{\sigma_f^2}
 (\nabla\mu_{gs})(\nabla\mu_{gs})^T+H_{\rm timing}.
\]

Include the RF cross blocks and the V16 timing precision. Reusing a 200 Hz
Fisher matrix or the original 1 s relative prior while scoring V16 changes the
optimizer behavior and can impair convergence.

The archived damped Fisher/SQP routine starts damping at 10⁻⁶. It adds damping
times `diag(max(diag(H),1))`, solves a reduced Newton step if feasible, otherwise
solves the constrained quadratic step with SLSQP. It allows six damping
attempts, increasing damping tenfold on failure. Backtrack fractions
`1,1/2,…,1/8192`; accept an actual-loss Armijo decrease with coefficient 10⁻⁴,
then reduce damping by five, down to 10⁻¹⁰. There is a narrowly bounded
roundoff exception for a scaled step ≤10⁻⁵, objective within 64 floating-point
epsilons of flat, and at least 10% improvement in the stationarity audit.

Convergence requires a scaled constrained first-order residual at most 10⁻³.
At an active timing or position boundary, audit the gradient against active
constraint normals rather than demanding the raw gradient be zero. A time
limit or inability to find a descent step is not automatically convergence.
The companion source includes the exact `constrained_fit.py` audit.

### 13.4 Starts and budgets that produced the reported snapshot

These results did not come from one zero initialization. The exact experiment
shares archived starts across models and RF arms, repricing every start under
the current objective. A parameter vector's old score must never be reused
under different likelihood settings.

| Stage | Saved sweep policy |
| --- | --- |
| Shared initial seeds | 12 results: six previous timing-penalty variants × two RF arms |
| Roof fits | Two starts, up to 3 s each, position fixed |
| Initial position searches | Three starts, up to 6 s each |
| Distinct second spatial start | Prefer at least 100 m from the best repriced seed |
| Initial polishing | Up to two 15 s stages, stop early on stationarity |
| Cross-model starts | Reprice all 36 initial cases, 18 configurations × two arms |
| Cross-start polishing | Up to two 15 s stages |
| Matched continuation | Up to 20 s SLSQP plus 10 s Fisher, stop early on stationarity |

Every scan and RF pair receives matched maximum budgets. The solver retains
the best feasible state by **its own objective**, never by distance from the
known roof. The continuation uses SLSQP with at most 300 iterations and
`ftol = 1e−11`, followed if needed by the Fisher routine. The dependency receipts
record the exact seed sources and hashes.

For a clean new implementation, use multiple feasible spatial/timing starts,
including a roof fit and displaced starts, and the same budget in both RF arms.
That implements the same model but is a **new search protocol**: it is not
guaranteed to land on these exact saved local optima without the archived seed
pool. Wall-clock limits also make bit-for-bit optimizer trajectories
hardware-dependent. Compare equations first, then search quality separately.

### 13.5 What the position gradient means

The profiled score is `J*(x)=min_nuisance J(x,nuisance)`. At a smooth, converged
nuisance optimum on a stable branch, its gradient is the spatial partial
derivative of `J` at that fitted nuisance state. The envelope theorem removes
the need to differentiate the fitted nuisance solution explicitly.

The code jointly optimizes position and nuisance inside each scan to avoid a
complete inner optimization at every spatial line-search evaluation. Fixed-site
probes still refit nuisance. Multiply a gradient expressed per kilometre by
0.1 to report score change per 100 m. The downhill arrow is `−∇J*`, not an
estimated physical displacement or an uncertainty ellipse. Switching local
minima, a horizon crossing, or unconverged nuisance can invalidate a simple
smooth-profile interpretation.

## 14 Results and their interpretation

![Matched results and frequency versus position error](figures/07-results.png)

### 14.1 Matched cohort summary

The C1 rows below are the controls from the **same polished score sweep**.
They are not the later C1-Q1 smooth-visibility experiment.

| Model and RF arm | Median error m | Mean error m | 90th percentile m | Below 1 km | Converged | At 4 km boundary | Median posterior RMS Hz |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| C1 fitted c | 1225 | 1571 | 2589 | 3/16 | 15/16 | 0/16 | 98.0 |
| V16 fitted c | 1167 | 1609 | 2570 | 4/16 | 16/16 | 0/16 | 92.8 |
| C1 c = 0 | 1531 | 1887 | 3815 | 3/16 | 14/16 | 2/16 | 152.3 |
| V16 c = 0 | 1280 | 1763 | 3391 | 4/16 | 15/16 | 1/16 | 138.4 |

V16 improves the cohort median relative to C1 by about 4.8% with fitted `c`
and 16.4% with `c = 0`. It does **not** improve every summary: fitted-`c` mean
error is slightly worse. In fitted-`c` paired scan comparisons, six improve
and ten worsen by more than 1 m; the median paired change is about **+47 m**.
A lower median across a cohort is not the same as a typical paired improvement.

The `c` ablation separates frequency fit from localization. Fitted `c` has
smaller median frequency RMS and smaller median position error for V16, but
individual scans can prefer `c = 0` by a large amount. Do not select an RF arm
separately for each scan using the known position and call the resulting minimum
a validated model.

### 14.2 Per scan population and position error

| Scan | Passing windows | Associated windows | Satellites | V16 fitted c error m | V16 c = 0 error m |
| --- | ---: | ---: | ---: | ---: | ---: |
| N01 | 2728 | 2444 | 30 | 272 | 802 |
| N02 | 2239 | 2001 | 26 | 1143 | 1705 |
| N03 | 2547 | 2162 | 30 | 987 | 1177 |
| N04 | 3428 | 3182 | 29 | 942 | 2930 |
| N05 | 3542 | 3256 | 38 | 2574 | 535 |
| N06 | 2842 | 2601 | 20 | 2557 | 2553 |
| N07 | 3296 | 3008 | 30 | 1079 | 1312 |
| N08 | 3069 | 2808 | 25 | 991 | 456 |
| N09 | 3416 | 3165 | 28 | 3141 | 4000* |
| N10 | 3045 | 2814 | 30 | 1692 | 2088 |
| N11 | 3027 | 2766 | 27 | 1190 | 1190 |
| N12 | 3065 | 2764 | 27 | 2566 | 1247 |
| N13 | 2636 | 2362 | 32 | 1026 | 1247 |
| N14 | 2722 | 2538 | 32 | 1106 | 615 |
| N15 | 2103 | 1873 | 22 | 2549 | 2496 |
| N16 | 3070 | 2866 | 26 | 1926 | 3852 |

`*` N09, `c = 0`, is at the 4 km boundary and does not meet the convergence
criterion. It is not an established unconstrained minimum. All values are
best-found local results in the specified disk. Full precision and session IDs
are supplied in the CSV files.

![Position outputs and actual residuals](figures/08-position-output.png)

### 14.3 Define residual metrics before comparing them

The original-owner RMS preserves the discrete greedy identity for every retained
window, even if the final soft model has moved its probability elsewhere:

\[
R_{\rm owner}=\sqrt{\frac1G\sum_g e_{g,\operatorname{owner}(g)}^2}.
\]

The posterior-weighted RMS is

\[
R_{\rm soft}=\sqrt{\frac{\sum_{g,s}z_{gs}e_{gs}^2}{\sum_{g,s}z_{gs}}}.
\]

The latter downweights mismatches explained as clutter and permits a different
selected satellite to explain a window. It is not the RMS of every original
greedy assignment, nor evidence that all associated NORAD IDs are right. A
strong soft assignment in these diagnostics means the largest satellite
responsibility exceeds 0.5. That diagnostic threshold is not a loss-function
gate. Original GLRT margin is not a continuous V16 window weight.

N01 illustrates why soft and owner metrics need separate names: its fitted-`c`
solution has 2,444 input windows, approximately 91.17 Hz posterior-weighted RMS,
and about 272 m position error. Its loss is approximately 27,591.7404, consisting
of 26,553.7904 data NLL and 1,037.9500 timing penalty. Common timing is about
0.3976 s, and relative timing RMS about 1.2478 s—well beyond the prior's 0.15 s
width, but permitted because the prior is soft. The likelihood improvement can
outweigh even a substantial timing cost; the prior is not a hard timing cap.

## 15 Training and evaluation populations

| Stage | Fitted or selected on | Evaluation used here | Role of a subset |
| --- | --- | --- | --- |
| Initial acquisition | IQ in one probe; even pilot symbols for fine search | Odd pilot symbols for basin verification | Within-probe diagnostic, not held-out scans |
| Fractional GLRT and three-pass refinement | Same probe's IQ | Same IQ scores | In-sample detector statistic |
| Top-one selection | Original passing candidates in each group | Same group | Strongest margin only |
| Bootstrap track shapes | Long positive-margin top-one tracks | Same tracks | Initialization, not final fit data |
| Receiver prefit and postfit | All passing top-one scan windows | Same complete set | No held-out windows |
| Nonlinear RX correction | Visible high-responsibility residuals within 600 Hz | Same supported residuals; correction then applied to full scan | Explicit quality support gate |
| Satellite discovery and selection | All passing top-one scan windows at roof | Same scan coverage | Coherent-segment gates define usable support |
| V16 position fit | All fitted-c-associated top-one windows | Same windows for NLL/RMS; roof for position error | Unassigned/nonpassing windows excluded |
| Hyperparameter comparison | Repeatedly inspected N01–N16 cohort | Same cohort | Development comparison, not untouched test data |

Old artifact fields such as `locked_test` describe the original cohort plan;
subsequent repeated model selection on these scans means they are not an
untouched test set for V16. Likewise, a starting vector originating in an old
fold does not make the current full-window fit cross-validated. Conversely,
calling calibration “full data” does not mean the spline fits every residual
equally or that unassociated windows enter the final position likelihood.

## 16 Computational complexity and efficient implementation

The dominant raw-IQ expense is template correlation. A naive acquisition scans
all CFO/epoch combinations independently and wastes most work. Reuse template
samples, sliding correlations, receive-energy prefix sums, folded frame indices,
and frequency rotation banks. An optimized implementation may use native kernels
and short autocorrelation spectra while retaining the direct equations as tests.

Three-pass refinement requires at most 13 GLRT evaluations per original passing
candidate: about 1.75 million calls for this 134,835-candidate cohort. It is
independent across probes, but candidates from one probe should share the loaded
IQ rather than repeatedly decompressing the same visit. Checkpoint each visit
with input and implementation hashes. Do not use satellite guidance to prune
this stage if claiming orbit-free refinement.

Propagating the complete catalogue is a one-time cost per scan. Cache ECEF state
arrays, then interpolate cheaply during discovery and optimization. Discovery
cost is roughly proportional to windows × near-visible satellites × coarse
timing steps, plus local mode refinements. Process candidate blocks to bound
memory; the saved discovery uses blocks of 16 satellites. Cache eligible-row
lists and a reverse row-to-mode index so a greedy update touches only modes
whose available support changed.

For final position fitting, with `G` retained windows and `K` selected satellites:

- Prediction and singleton likelihood cost `O(GK)` per evaluation.
- The sparse timing Jacobian has one satellite timing entry per window/satellite
  pair plus a small shared block; avoid a giant dense observation Jacobian.
- The fitted parameter count is `K+7`, typically a few dozen, so a dense
  parameter-space linear solve is inexpensive relative to repeated prediction.
- There is no exponential subset-state HMM cost for this top-one likelihood.
  A future true multi-peak finite-set model would have a different complexity.

V16 has moderate model complexity, approximately **3/5** on the earlier
qualitative scale: soft identity uncertainty plus shared nuisance and position
fitting, but no learned antenna map or time-varying latent process. Compared
with baseline T1-AT it adds tuning burden, not new parameter types. No runtime
speedup claim follows from its smaller sigma; convergence can become harder.

## 17 Reimplementation and verification checklist

### 17.1 Minimal independent interfaces

Keep physical evidence and fitted hypotheses separate:

```text
read_probe(source_id) -> IQ, sample_rate, actual_RF, timing/counter evidence
acquire(IQ, template, tuning_geometry) -> candidate epoch/CFO basins
glrt(IQ, epoch, center, edge) -> exact, control, margin, tracking_CFO
refine(candidate, IQ) -> new frequency/epoch, trace, status, same identity
top_one(candidates_by_window) -> one observation per passing source group
build_bank(TLE_snapshot, origin, times) -> ECEF positions/velocities, validity
predict(position, times+satellite_shifts, RF) -> Doppler, visibility, Jacobian
calibrate(all_top_windows, seed_bank, known_roof) -> frozen RX baseline
discover(all_top_windows, whole_bank, calibration) -> finite timing-mode pool
select(mode_pool) -> chosen modes, exclusive window owners, search trace
freeze(selected_windows, selected_bank, fixed_RX_baseline) -> position input
score(position_input, parameters, V16_settings) -> NLL, gradient, probabilities
optimize(shared_starts, constraints) -> best feasible state and stationarity
```

Raw-IQ and catalogue adapters should not be hidden inside numerical scorers.
The oracle repositories mentioned in historical template provenance are not
runtime dependencies. Recording access remains read-only. A reimplementation
can use a standard SGP4 library, but must match frame, timing, RF and alias
conventions before interpreting any numerical differences as model improvements.

### 17.2 Required numerical tests

1. **Template test:** decode the included pilot constants, synthesize both
   templates, and compare sample values and symbol ordering with the source
   appendix. Test upper/lower edge, exact/control roll, and complex64 rounding.
2. **Acquisition test:** inject a known pilot with CFO and epoch, verify search
   bounds, retained basins, sign and frequency reference. Test the frame seam
   and unsupported interpolation guards.
3. **GLRT test:** a 64-symbol pure phase ramp at an FFT-grid frequency must
   produce the right residual and normalized statistic 1. Multiplying all
   IQ amplitudes by a constant must not alter the normalized score.
4. **Refinement test:** compare all 13 attempted points and the incumbent rule.
   Preserve candidate counts/IDs on success and failure; never count alias
   hypotheses as independent windows.
5. **Timing test:** counters, probe starts, support-center UTC and fractional
   epoch must reproduce original exports. Do not reconstruct time from visit
   count times a nominal dwell.
6. **Orbit test:** compare fixed-point Doppler and elevation against the stored
   ECEF bank; check the Earth-rotation term and actual RF scaling. Test timing
   derivatives on both sides of a bank node, avoiding the knot for central
   finite-difference checks.
7. **Selection test:** verify window uniqueness, one mode per ID, every segment's
   support/gap/span gates, and strict score improvement for accepted repairs.
   Recompute cached marginal support to detect stale-cache errors.
8. **Likelihood test:** responsibilities plus clutter sum to 1, invisible
   satellites have zero responsibility, and alias-period shifts leave likelihood
   invariant. Compare exact multi-peak code restricted to one peak against the
   singleton equation.
9. **Gradient test:** compare finite differences with analytic frequency,
   receiver, timing, RF and position derivatives at smooth interior states.
   Reprice every proposed step using the actual loss, not just its quadratic
   approximation.
10. **Scope test:** matched RF arms must have identical window IDs, satellite
    bank, frozen baseline, priors, bounds and maximum search budget. Save
    convergence and boundary flags, not just position distance.

The included [test_reference_math.py](test_reference_math.py) directly tests
wrapping, timing-basis gauge, a synthetic GLRT tone, likelihood responsibilities,
prediction gradients and the saved numerical reproduction receipt. It is a
small report-owned test suite, not all ten categories of full pipeline tests.
It also checks report links, cohort accounting and source-appendix integrity.

### 17.3 Reproduce the report without refitting

From this repository's root, using its existing NumPy/Matplotlib environment:

```bash
.venv/bin/python reports/2026_10_06_v16_implementation_report/build_report.py
.venv/bin/python -m pytest -q reports/2026_10_06_v16_implementation_report/test_reference_math.py
```

The builder reads saved results and the frozen input artifacts, produces the
figures and CSVs, evaluates the independent final equations, and renders HTML.
It does not perform acquisition, model fitting, or RF collection. The original
IQ and full orbit banks are not redistributed inside this report package; the
hash manifest identifies the local archives needed for exact data replay.
`--snapshot` additionally rebuilds the source appendix using read-only access
to the named immutable installed release and archived research scripts.

For exact historical IQ processing use release
`47e2705e437722daa5e6d6bb1c252d54b7a21dbc` and the file hashes in the appendix,
not whatever later acquisition changes happen to be in the working tree.
The pilot constants and equations suffice to implement the numerical kernels;
production storage and capture contracts are separate from those kernels.

Key stage references:

| Stage | Repository reference |
| --- | --- |
| Export candidate evidence | [export_observations.py](../2026_10_04_ds13_18_scan_benchmark/export_observations.py) |
| Orbit-free refinement | [refinement.py](../2026_10_04_ds13_18_scan_benchmark/refinement.py), [run_refinement.py](../2026_10_04_ds13_18_scan_benchmark/run_refinement.py) |
| Orbit bank | [orbit_bank.py](../2026_10_04_ds13_18_scan_benchmark/orbit_bank.py) |
| Bootstrap | [bootstrap_tracks.py](../2026_10_04_ds13_18_scan_benchmark/bootstrap_tracks.py), [seed_timing_variant.py](../2026_10_04_ds13_18_scan_benchmark/seed_timing_variant.py) |
| Full-data calibration and association | [full_data_calibration.py](../2026_10_04_t1_at_v1_replication/full_data_calibration.py), [seed_restart_pipeline.py](../2026_10_04_t1_at_v1_replication/seed_restart_pipeline.py) |
| RX correction | [receiver_spline.py](../2026_10_03_ds13_coverage_goal/receiver_spline.py) |
| Timing proposals | [adaptive_discovery.py](../2026_10_03_ds13_coverage_goal/adaptive_discovery.py); exact greedy adapter in the source ZIP |
| Final prediction | [prediction_jacobian.py](../2026_10_02_multiscan_localization/prediction_jacobian.py) |
| General finite-set model | [finite_set_likelihood.py](../2026_10_02_multiscan_localization/finite_set_likelihood.py) |
| V16 settings and experiment | [position_score_sweep.py](../2026_10_04_t1_at_v1_replication/position_score_sweep.py) |
| Optimizer and continuation | [convergence_fisher.py](../2026_10_04_t1_at_v1_replication/convergence_fisher.py), [polish_position_score_sweep.py](../2026_10_04_t1_at_v1_replication/polish_position_score_sweep.py) |

## 18 Limitations and the next defensible comparison

The principal limitation is not lack of a low residual: a wrong or imperfect
orbit/calibration combination can fit frequency well while moving the optimum
away from the roof. Receiver lines, RF dependence, satellite timing and position
can partially compensate for one another. Tightening priors changes that
tradeoff; it does not identify which physical source of error is correct.

Other limitations affect what “91% explained” means:

- The denominator is passing top-one windows, not all scheduled probes, all
  original candidate records, or all simultaneous emitters in the IQ.
- The original detector gate, top-one choice, quality gates and association
  selection all condition the data population. They are not fully modeled in
  the likelihood's simple nonempty-set normalization.
- High responsibility only compares the selected satellite bank. A plausible
  alternative discarded upstream cannot compete in the final fit.
- The receiver baseline and memberships were learned at the known roof.
  Search within a roof-centered disk is a local consistency experiment, not
  unconstrained geolocation from no location information.
- The hard horizon, midpoint observation approximation, fixed altitude, TLE
  errors, clock/frame approximations, and unmodeled transmitter behavior can
  leave structure in residuals. None is diagnosed uniquely by low RMS alone.
- Converged means locally stationary under the stated constraints. It does
  not certify the global minimum, correct association, or calibrated uncertainty.

The next clean comparison is to freeze this exact V16 specification and one
alternative before examining new scans, preserve matched fitted-`c` and `c = 0`
arms, and report coverage, owner/soft residuals, timing costs, local-minimum
stability and position error separately. Any new visibility prior, association
replacement after positioning, or additional IQ refinement should have its own
variant name and matched input/search controls. This keeps improvements in the
detector, association search and position model distinguishable.
