# Implement and test joint receiver-informed satellite association

User authorized implementation and testing after reviewing the receiver
association design. Preserve the overarching objective of improving causal
single-scan DS11 positions. Successful software tests alone do not establish
accuracy improvement. The app goal is active: improve DS11 single-scan position
error by better modeling techniques. It remains unfinished until the scientific
outcome and validation support completion.

Required work and completion evidence:

The full existing source-policy trade-off audit now explicitly covers44
attempts/43 matched pairs: pooled median worsens2706→2807m, mean improves
3609→3267m, andP90 improves7340→6308m. Additional-panel median/mean/P90 all
regress; that failed replication remains binding. Two aggregation tests and228
existing source bindings verify. The user has been asked which accuracy metric
to prioritize; do not treat silence as permission to replace the frozen median/
replication requirements or promote a model selected on exposed pooled errors.
The earlier antenna altitude/datum question also remains pending.

The newly supported2.5MS/s DS11 pilot in `two5_position/` is complete and fails
both frozen family gates. All24 child fits terminate;10/12 model-record cells
have qualified selections. Family0 improves original15/30 (1361→1222m and
8309→7549m versus contemporary Doppler), but additional11 worsens6035→6052m;
its median consequently worsens. Family1 improves original24 (5931→5791m),
worsens original31 (8130→8359m), and additional9 remains unqualified under both
arms. The original additional9 failure is retained. All six exact-partition/
gradient preflights pass and four component tests pass. Receiver coefficients
remain frozen; no smaller subgroup or model strength is selected after scoring.
These results close the conditional whole-source acquisition coverage gap,
not the positioning objective or the physical absence/clutter requirement.

The extra-donor receiver transfer is complete and passes on all four records.
All12 timing starts qualify at the frozen N23 horizontal location. Selected
states replay the banks within the existing1e-8 tolerance. The original
family0/1 receiver coefficients remain unchanged; signed geometry beats every
control on each donor with121/159 source/RF wins. Six component tests and568
recursive source bindings verify. This closes the missing separate-record
conditional receiver validation for the two2.5MS/s settings. It does not
calibrate physical00-state absence or prove position improvement. Next prepare
a bounded DS11 pilot for these settings with a frozen estimator and controls;
preserve the known additional-index9 baseline qualification failure rather than
silently removing that recording from denominators.

The extra donors now pass recorded availability and numerical-export checks.
Public metrics manifests bind exactly to the loaded analysis digests and were
finalized20.2–21.4hours before DS11. Selected archive requests obey the existing
505second guard and local file mtimes precede each donor capture. All eight
track/bank exports finish in at most56.01seconds each;64/61/58/58 tracks and
2995 candidate-track slots verify, including finite arrays and pinned provider
identity. Four selection/availability tests pass. Next: fit each new donor's
timing at the already frozen N23 station geometry, export inferred source
visibility, and test the existing family0/1 receiver coefficients without
retuning them against these recordings. No DS11 position has changed.

The remaining-family review found useful work independent of pending altitude.
`extra_donors/` inspects the first four metadata-eligible candidates from the
previously unreviewed33. All four checks succeed in at most20.84seconds each;
two match family0 and two family1 exactly. Each has64 retained tracks,32 per RX.
Two selection tests pass. They are prospective additional calibration sources,
not yet qualified donors: next verify exact causal orbit support and whether
the loaded analysis evidence was available before DS11, then export physical
source/geometry evidence. No extra receiver coefficients or positions are fit.

The independent fixed-height implementation in `../fixed_height/` is prepared.
Two tests pass for nonzero-height gradients, held isolation, zero-height parity
and rejection of a free fourth parameter. Real-data preflight on scans0/16
reproduces original predictions and training scores exactly; maximum gradient
parity discrepancy is9.7e-13 and finite-difference discrepancy3.3e-6. No height
is selected and no new position is fitted. The pending independent antenna
altitude/datum is required before the nonzero-height comparison can proceed.

Independent altitude evidence was revisited after the orbit-scale screen. The
station authority still has null altitude/datum. A user question about measured
antenna height and its datum is pending. Read-only public queries in
`../altitude_evidence/external-evidence.json` return a USGS terrain value54.5716m
(reported acquisition2018-03-02, resolution1m) and NOAA GEOID18 undulation
-32.477m. Neither measures roof/mount height; NOAA's conversion is NAD83/NAVD88,
not directly WGS84. The USGS response does not explicitly identify its vertical
datum, and acquisition date is not publication/availability evidence. Do not
select a fixed antenna altitude from these responses alone or launch a
reference-error-driven height sweep. Existing free-height results remain failed.

The distinct historical orbit-state age uncertainty screen now passes its
exploratory exposed validation:67/120 source wins, mean/median log gains
0.04886/0.07483nats against a fitted constant. Its frozen independent next-date,
new-object confirmation finds zero qualifying epoch triplets among256 sampled
satellites. This is insufficient confirmation, not proof the scale relation is
false. No DS11 noise weights or orbit corrections follow, and no alternate
cutoff/cohort is selected. Any continuation must distinguish orbit-state proxy
uncertainty from independent Doppler noise and supply independent validation.

The unanchored phase-gap feasibility test in `phase_gap/` now also fails: all72
eligible source/RF clock fits qualify, but donor17 median held hit fraction is
60% at donor16's19.486us threshold, failing both the80% hit requirement and the
13.333us tolerance ceiling. No raw non-detection labels follow. This closes
the simple shared quadratic phase extrapolation route; explicit00-state
evidence remains uncalibrated. Keep that requirement open and do not promote
conditional anchored detections as a complete four-state physical likelihood.
The subsequent matched fragment-clock diagnostic also supplies no consistent
repair: donor16 median error worsens5.98→13.88us, donor17 improves4.34→3.08us
on only the supported subset. Retain the17/63 unmatched candidates explicitly;
their313/182us median errors show why restricting evaluation to supported
fragments would hide the hard cases. No phase-based absence census follows.

The soft cross-RX timing factor is implemented and tested in `epoch_position/`.
All four family2 fits qualify but neither position improves. Its43 supported
edges per scan agree with existing identities, so increasing association weight
without new evidence is not justified. Keep the baseline and active objective.
The DS10 frame-phase feasibility audit is complete in `frame_evolution/`.
Direct range/c fails its comparison; reversed curvature fits better, but a
per-track quadratic clock fits better still. A source-pooled training relation
has only a small improvement over constant curvature on the second recording.
Further clock/source controls pass on five additional settings, but measured
curvature scatter implies weak local position information (15–335km optimistic
fixed-nuisance diagnostic scales). Do not strongly weight phase as direct range.
Timing-linked raw detections are now calibrated in `raw_visibility/` and tested
in the exact-assignment `raw_position/` pilot. Independent geometry prediction
passes, but both qualified DS11 timing-geometry positions worsen slightly. The
baseline remains, with no weight tuning or expansion of that failed model.
The phase-residual/Doppler-slope transfer audit is complete and fails in all six
families. No such correction is applied to DS11. Current next step: execute the
previously authorized, separately labeled offline orbit comparison in
`../offline_orbit_pilot/`. The frozen supported-update selection chooses22/23.
The offline replay and eight fits are complete: scan23 improves3579→929m,
while scan22 worsens2813→2898m; all starts qualify. Four/eight inferred identities
change and both held scores improve. The16-fit crossed offline mechanism
ablation is now complete. The large gain on23 survives original fixed labels
(3578→486m with later orbit states); changing only labels gives3403m. Scan22
remains mixed. No best geographic cell is promoted. The independent historical
orbit-forecast calibration is now complete:921 training cases,396 time/object-
disjoint validation cases, and a bounded coefficient0.8080. Median reference-
proxy error improves16.9%, mean only3.3%, failing the frozen5% requirement for
both. All12 corrected exports succeed and three component tests pass. No DS11
state correction follows this failed gate. Next work must identify a distinct,
independently testable causal mechanism; do not relax this predictor's gate or
retune its bounds against the observed validation errors.
Do not reuse the failed residual-derived one-direction
orbit prior unchanged or learn correction strengths from DS11 errors. Offline
gains cannot complete the primary causal goal or justify future target inputs.

- [x] Build source-specific paired hypotheses from same-time, exact-RF observing
  opportunities. Preserve unpaired hypotheses and unknown opportunities. Verify
  candidate identity mapping and handle acquisition candidates reused by tracks
  without treating those rows as independent measurements.
- [x] Implement normalized soft joint cross-RX assignment, with mutually
  exclusive matching alternatives and satellite mixtures. Verify against exact
  enumeration, permutations and zero-information controls.
- [ ] Implement shared-strength four-state receiver detection likelihood,
  explicit missed detections/clutter and time-dependent source presence. Treat
  receiver mapping as user-confirmed working geometry; keep beam width distinct
  from nominal boresight separation.
- [x] Calibrate only on disjoint existing recordings with compatible RF/hardware.
  Preserve calibration provenance and missing support. Avoid fitting beam or
  orbit priors to DS11 reference position errors.
- [ ] Couple Doppler, receiver geometry and station position. Establish a
  zero-geometry parity control and numerical derivative checks. Start with fixed
  causal states, then test bounded satellite-shared orbit uncertainty separately.
- [x] Run bounded DS11 pilot comparisons against Doppler-only, receiver-only,
  receiver-swap and candidate-geometry permutation controls. Seal training
  selections before held/geographic scoring; preserve all failures.
- [ ] Report association ambiguity, held-source/time-block scores, horizontal
  error and execution receipts. Broader confirmation follows only a passing
  pilot. If the method fails, report that result and retain the baseline.

Completed conditional-model evidence: exact matching/ownership, compatible
DS10 calibration and receiver transfer controls, full position coupling with
derivative/parity checks, six-scan development extension, one compatible
separate-record confirmation, and exact physical-identity marginal audits.
The independent-state model passes the six-scan development gate but fails
separate-record confirmation, so the baseline remains retained. A normalized
time-correlated conditional receiver model also completes all seven recordings
and fails its frozen accuracy gate (3/7 wins, 0.81% median reduction, additional
record regression). All 25 component tests pass; 60/63 fit/control cells qualify.
These conditional models do not complete the full absence/clutter/presence
requirements above, and do not justify declaring the accuracy goal complete.

The subsequent exact whole-source implementation now permits multiple track
fragments per receiver and satellite/RF, retaining all candidate assignments.
Its pilot also fails: the separate record still regresses and two cells fail
optimizer qualification. An exact DP acceleration repairs the one timeout,
with parity verified and the failed attempt retained. There are now 34 unique
passing component tests. Calibration coverage has been inventoried across all
eight acquisition settings, rather than redefining the goal around the initial
5MS/s subgroup.

A provenance audit found one contributor to the old pooled calibration geometry
was finalized after the earliest target, despite its RF capture being earlier.
The new qualified N23 geometry excludes it and uses only available seed panels.
Receiver calibration has now been rebuilt across all eight acquisition
settings using 23 available donors. All six settings with separate donor
validation pass the frozen conditional receiver screen (292/379 source wins).
The two 2.5 MS/s settings still lack validation support; 33 other earlier
recordings are identified for RF/track eligibility review. All 39 unique
component tests pass. The rebuilt coefficients subsequently fail an eleven-record
position pilot: 3/11 wins and worse median/P90 in both cohorts. All 22 processes
finish but only 11 fits qualify; line-search failures are preserved. A separate
fixed-geometry association-only experiment also fails on the same panel:
3/11 wins, original median 2291.6→2517.8m, additional median essentially
unchanged, and worse P90 in both cohorts. It qualifies 21/22 fits; the remaining
cell fails its derivative audit. Inspect association posterior changes before
another likelihood variant, rather than assuming receiver calibration success
will translate to position accuracy. All failures stay recorded.
The old failed accuracy trials remain unchanged. See the README,
acquisition_calibration/summary.json and
causal-calibration-geometry.polished.json. The goal remains active.

Exact posterior diagnosis now covers all 668 tracks in the eleven-record panel:
both receiver models remove majority probability from 40 original identities,
including 24 originally at ≥.99 Doppler probability. This is not verified label
truth. A calibration-only constant-emission persistence screen finds timescales
4.95–11.12 seconds. Four families pass the temporal geometry gate, two fail, and
the two 2.5MS/s families remain unsupported. Next test time-correlated whole-source
inference with calibration-gated Doppler fallback, keeping every setting in the
evaluation. That temporal policy is now tested: all 22 fits qualify, but
original median error rises 2291.6→2351.8m and additional median rises
2568.4→2585.0m. Both P90s worsen and only two records beat the refitted Doppler
control. The isolated additional-index3 gain 613→227m does not pass the gate.
Posterior majority-loss counts fall 40→19 overall, but only 23→18 on records
that actually use temporal geometry; fallback explains the rest. A fixed-position
receiver-only ablation now separates grouping effects from geometric evidence.
No lower position-error result has yet been established.

That ablation is complete: at identical temporal-policy positions, Doppler,
receiver-only and signed geometry lose majority probability for 6/16/19 original
identities. The counts for originally ≥.99-probable identities are 0/10/10, with
the same ten changed under both receiver models. Next test geometry evidence
relative to the receiver-only likelihood, with exact zero-geometry parity,
before further antenna/timing adjustments. These are inferred posterior labels,
not authenticated satellite identifications; all prior failed gates remain failed.

The geometry likelihood-ratio pilot is complete: all22 fits qualify, equal
emission models recover Doppler exactly within numerical tolerance, but the
accuracy gate fails. Original median2291.6→2291.8m and additional2568.4→2570.5m;
both P90s worsen slightly. Posterior majority-loss counts fall19→7, with none
of the originally ≥.99-probable identities changed. That repairs the diagnosed
association effect without proving lower positioning error. The baseline remains
retained; full detection/clutter/source-strength selection assumptions still
need investigation. Do not retune this failed policy against reference errors.

No new RF collection, post-capture orbit input in primary results, production
deployment, or immutable contract/golden fixture change is authorized by this
research implementation. Existing observations and original banks stay intact.
Each numerical child is bounded to 90s unless a separately declared input export
needs its existing 180s allowance. At most three single-thread workers.
