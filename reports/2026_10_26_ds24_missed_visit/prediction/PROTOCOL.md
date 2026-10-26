# Sparse causal prediction, development v1

Freeze this source, tests, whole-recording split, target panel and evaluation
archive before prediction or target-outcome analysis. Only the twelve development
recordings in ../split.json are opened. Do not open validation tracking files.
For each development recording choose the processed RX0 same-channel visit
nearest 20%, 40%, 60%, and 80% of the scan's native-counter span (ties earlier),
on CH1/4 controls and CH5–8. Keep both RX and every missing cell. Selection uses
no candidate values. There are 288 paired target windows and 576 receiver cells.
Keep archived target candidates in a separate sealed evaluation file.

Each cell uses at most twelve strictly earlier same-channel/RX/edge processed
visits within 4.5 seconds of target start. Missing detections do not terminate
a history. Keep original rank 0..8 candidates with margin >=0.025. Coalesce
only candidates within 2 circular timing samples and 200 Hz, retaining the
lowest original rank. Every distinct measured candidate may start a one-donor
track. Process visits chronologically. Extend each existing track by every
compatible candidate; retain missed tracks and new births. There are at most
eight retained modes and at most two paths per latest donor. Deterministic
priority is latest donor first, then more donor visits, then lexicographic
original ranks/IDs. Keep counts of pruned modes and alternative associations.
No target evidence, graph fit, satellite, TLE, position or GPS enters inference.

A candidate pair may associate when CFO difference <=500+6000*dt Hz and
counter-propagated timing difference <=4+200*dt samples. Multi-donor ordinary
linear fits must have |CFO rate|<=6000 Hz/s, |timing rate|<=200 samples/s,
maximum CFO residual <=500 Hz and maximum timing residual <=4 samples.
Multiple compatible extensions remain alternatives. These are engineering
association assumptions, not physical identity truth. A sole donor has zero
estimated rate with explicitly broad rate uncertainty; it is not evidence of
zero physical rate. Original score orders neither associations nor tracks.

Define donor CFO at the declared nominal midpoint counter start+100000. This
is an explicit reference convention, not a claim that each pilot's effective
weighting center is exactly the midpoint. Persisted epoch is a frame start
relative to the window origin: fit circular timing phase at the window START
counter, separately from CFO's midpoint reference. Each target/half prediction
evaluates CFO at its own midpoint and timing phase at its own START, then
subtracts its exact start-counter offset modulo rate/750. A half-origin epoch
therefore includes timing_rate*half_start_offset, while its CFO includes
CFO_rate*half_midpoint_offset. Publish both reference counters explicitly.
The existing scorer treats timing epoch as constant over its support; changing
timing phase within the 10ms half is an explicit approximation (up to 2 samples
end-to-end at the 200sample/s association bound). This predictor does not
pretend to correct that intra-window time warp. Per-frame propagation can be
requested with each frame's start and CFO reference counter.

Multi-donor forecast sigma is max(floor, donor residual RMS)*sqrt(1+leverage)
plus half the declared acceleration allowance times horizon squared. Floors
are 75 Hz and 0.75 sample; acceleration allowances are 500 Hz/s² and
10 samples/s². One-donor sigma is hypot(floor, rate_sigma*horizon) plus the
same acceleration allowance; rate sigmas are 4000 Hz/s and 150 samples/s.
Three sigma is a heuristic search width, not calibrated probability coverage.
Publish uncapped widths so downstream bounded timing/CFO searches can report
their truncated exposure honestly. Do not tune any values after evaluation.

The sealed archived-outcome survey reports donor opportunity, missed-visit
counts, ambiguity and mode caps, and target compatibility with forecast
timing/CFO. Evaluate original gatepassing target candidates only after all
forecasts are sealed. Report matched joint timing/CFO compatibility under
fixed thresholds timing {2,16,64,256} samples and CFO {100,500,3000} Hz, as
well as the heuristic three-sigma bands. These are descriptive associations
with already exposed full-window acquisition, not external signal truth,
successful recovered detections, a calibrated likelihood, or a FAR test.
Keep primary and any-mode counts separate. No raw IQ scoring is performed.

Each numerical stage uses BLAS1 and a 580-second bound; preserve missing and
failed cells, source hashes, and all denominators. No new RF, QNAP mutation,
runtime/golden-fixture edits, validation outcomes, geography selection, git or
publication. This is one fixed sparse-history predictor, not a parameter sweep.
