# Three additional segments in fast scan 223211

Scan `fast8-auto-20261016-223211-029a4eef-1-lower`, run
`fast-d626811aa789be76a985a4e33bd1e6f4`. RX1 means receiver 0. Times are seconds
from the qualified capture origin. Existing IQ only; no production inference,
collection, deployment, or scientific fixtures were changed.

All three intervals have coherent signals compatible with catalogue trajectories.
The leading candidates are **66854, 58362, and 57864** respectively. This is
conditional frequency evidence, not confirmed identities or improved localization.

![Conditional candidate matches and residuals](candidate-matches.png)

## Results at frozen production position and calibration

| Requested segment | Interval / fixed coherent subset | Associated in published fit, coherent subset | Candidate | Published candidate orbit shift | Best timing-only shift | Timing-only target RMS |
| --- | --- | --- | --- | --- | --- | --- |
| RX1 CH3, 40–60 s | 28 / 28 | 1 / 28 | 66854 | +5.163 s | −1.50 s | 307.7 Hz |
| RX1 CH2, 110–140 s | 36 / 35 | 5 / 35 | 58362 | +4.145 s | −1.25 s | 232.0 Hz |
| RX1 CH4, 250–280 s | 39 / 33 | 0 / 33 | 57864 | Not in final selection | −1.45 s | 203.3 Hz |

The first two candidates were already among the 32 selected satellites, but their
published timing fails to follow the requested tracks: RMS is 19,218 Hz for CH3
and 18,676 Hz for CH2. The third candidate was present in the full 821-satellite
screened bank but omitted from the final selection. The receiver correction and
position were held fixed throughout these comparisons. Orbit shifts are effective
model parameters; they do not demonstrate an acquisition timestamp error.

Targets were selected without orbit predictions using a circular quadratic
maximum-consensus model, with a 500 Hz inclusion tolerance, bounded slope and
curvature. Every original interval row, coherent row and excluded row is retained
in `summary.json`. CH3 needs curvature rather than a straight-line selector;
CH4 crosses the GLRT alias boundary. These are coherent-track diagnostics, not a
blind detector evaluation.

## What transfers, and what does not

Moving the first two candidates' timing alone is not a whole-scan repair. Their
existing sparse associations prefer the published timing:

* **66854:** the five published RX2 lower-band associations change from 159 Hz
  RMS to 12,314 Hz RMS under the CH3 target's timing. One published RX1 lower-band
  association changes from 55 Hz to 1,475 Hz.
* **58362:** nine published RX1 upper-band associations change from 146 Hz to
  14,404 Hz RMS. Two RX1 lower-band associations change from 97 Hz to 10,870 Hz;
  two RX2 lower-band associations change from 173 Hz to 3,905 Hz.

These memberships are the original model's assignments, not independently verified
satellite identities. They may include competing tracks or incidental crossings.
The conflict means reassociation and candidate support must be investigated before
changing a global satellite timing. It does not establish band-dependent emission
physics or an orbit error. Unlike the earlier scan's late-CH2 investigation, this
scan does not yet provide a demonstrated correction that transfers to RX2.

No saved RX2 top-one observation in the matching channel/time intervals falls
within 375 Hz of the three timing-only proposals: 0/20, 0/40 and 0/34 respectively.
This is a candidate-retention/compatibility check, **not proof that RX2 has no
signal**. Guided raw acquisition with negative controls would be the next test.

## Grouped prediction checks and independent elements

For each fixed target set, randomly assign whole two-second time blocks to five
folds using seed `20261016`. Candidate identity and orbit timing are selected
using training observations only; the held-out values are evaluated afterwards.
The search is identical for all satellites: −5 to +5 s in 0.05 s increments,
125 Hz frequency scale and a 2 s timing prior. Correlated observations in a block
remain together. Group and fold assignments are saved.

| Segment | Hugging Face timing-only held-out RMS, pooled | With additional constant target offset, pooled | Space-Track all-target timing-only RMS |
| --- | --- | --- | --- |
| CH3 | 334.3 Hz | 208.0 Hz | 333.7 Hz |
| CH2 | 270.8 Hz | 236.3 Hz | 223.2 Hz |
| CH4 | 203.3 Hz | 197.7 Hz | 200.5 Hz |

Each proposed identity wins every fold using both element providers. The independent
Space-Track snapshot yields different effective shifts: −1.95, −0.45 and −0.15 s.
That is another reason not to read the fitted shifts as literal receiver-clock
offsets. This comparison holds the production correction and position fixed; the
independent catalogue retains 816 candidates rather than 821, including one missing
catalogue number and horizon-screen differences, so this is not an isolated
provider-performance ablation.

CH4's Space-Track runner-up, 64021, fits at 259 Hz RMS versus 201 Hz for 57864.
The leading identity is stable across these folds, but this closer alternative
must remain in subsequent ambiguity checks.

Allowing a constant offset uses the same ±10 kHz bound and 4 kHz prior for every
candidate. CH3's best fit then uses approximately +5,572 Hz and +0.45 s timing;
the timing/offset tradeoff is substantial. Better residuals from that extra
parameter do not establish a physical transmitter correction. CH2 and CH4 gain
less from the offset model.

These folds share full-scan production calibration/position, and the requested
intervals and coherent subsets were inspected. They test conditional trajectory
prediction, not independent satellite identification or localization accuracy.

## Matched coefficient control

The same target rows, candidate bank, folds, grids, priors and budgets were also
scored with static RF coefficient `c = 0`, keeping all other fitted terms frozen.
All three leading identities remain unchanged. Timing-only pooled held-out RMS
becomes 331.1, 219.9 and 218.3 Hz, versus fitted-c values 334.3, 270.8 and 203.3 Hz.
The offset family largely absorbs the static RF correction.

This is a matched frozen-other-terms frequency diagnostic, not a fully refitted
zero-c localization analysis. No position optimization or position-accuracy claim
is made. Frequency-fit changes are reported separately from location accuracy.

## Raw-IQ and binding checks

Nine original probes were replayed: first, middle and last coherent observation
for each target. The reader verifies IQ digests; the saved probe's start counter
is asserted equal to the raw window's acquisition counter. Continuous GLRT replay
uses the saved integer epoch and fractional offset and independently refines CFO.

| Segment | Continuous replay minus stored CFO at the three probes |
| --- | --- |
| CH3 | +88.6, +144.6, +0.5 Hz |
| CH2 | +91.6, −43.5, +123.0 Hz |
| CH4 | +191.9, +82.6, +122.8 Hz |

These checks do not support a kilohertz-scale CFO error in the nine sampled probes.
They do not verify every probe, prove an identity, or settle the physical source
of the conflicting associations.

## Recommended next bounded step

For 66854 and 58362, use these coherent tracks as alternative timing/association
proposals, audit the original six/thirteen memberships, and score all unchanged
observations with both timing basins retained. For 57864, test candidate admission
against the saved alternative 64021. Any larger refit must retain matched zero-c
and fitted-c arms and independently report position error if ground truth is used.
Only after that, attempt receiver-guided candidate replay with negative controls.
The current evidence does not justify forcing these identities into production.

## Evidence and reproduction

`summary.json` binds the immutable input and terminal digests, reproduces the
saved numerical audit, records every search and support comparison, and includes
the nine raw-IQ receipts. `independent-elements.json` records the second element
snapshot and its searches. `baseline.npz` preserves the plotted observations and
published assignments. `manifest.json` hashes the bundle and scripts.

The scripts run in the existing `f141dbb30` shared scientific environment and take
`--output DIRECTORY`; they read the declared production source and write only to
that directory. `check_fast_segment_elements.py --plot-only` rebuilds the figure
from the saved conditional results without fitting. Tests cover wrapped-track
extraction, reproducible group separation, and exclusion of test measurements
from candidate/parameter selection. All four tests pass. Individual analysis runs
took under one minute; no radio collection or long campaign was started.
