# Candidate continuity, before satellite assignment

Frozen engineering prototype on the four complete saved synthetic sequences from
the preceding measurement experiment. No new detector calls, recorded IQ, RF,
satellite search, position/GPS or production changes. The synthetic trajectories
and their source labels are already exposed development fixtures; they are not
an independent validation population. Selector inputs contain no source labels.
Truth comparisons occur only after RF outputs are sealed.

The narrow `rf-candidate-windows/v1` port has sample rate and ordered windows.
Each window binds native observation/receiver-window ID, physical acquisition ID,
receiver/channel/actual RF, midpoint seconds, native start/origin counters and
all complete gate-passing deduplicated candidate rows. Each candidate binds ID,
rank, raw CFO, margin, local/global frame epoch and optional acquired CFO (unused
by selection). Full exported/excluded candidate ledgers remain alongside the port.
The existing dedup rule is unchanged: within120ns circular frame phase AND250Hz
circular CFO, retain descending margin, stable rank order. Original maximum-margin
winners must replay their exact old IDs, times, CFO and original graph assignment.

Window start is valid_start_counter+round(probe_start_ms*fs/1000), never packed
payload offset. Local epoch is integer_epoch_sample+fractional offset. The global
phase uses exact native integer arithmetic before adding local epoch:
`(((start-origin)*750) mod fs)/750 + local`, modulo fs/750. At10MHz this is
`(3*(start-origin) mod40000)/3 + local`, modulo40000/3. No fabricated UTC authority.
Synthetic integer-second visits happen to have zero counter-phase increment.

Compare original winners with a CFO-only candidate path and exactly the same
path objective augmented by epoch continuity. No incumbent satellite-family
restriction, orbital emission or family HMM is used. The previous HMM operated
on already selected winning CFOs, so it could not recover discarded peaks.

Candidates form a second-order time DAG within one RX/channel/RF lane. Native
time strictly increases along every edge: dt≥.15s and≤10s. CFO edges use nearest
circular increments at the unchanged227272.727Hz spacing, slope≤8000Hz/s.
Node reward is9+log(margin/max_margin_in_that_window), start penalty18, gap cost
.05*elapsed seconds. Margins enter an engineering cost, not a probability law.
For consecutive edge durations a,b and velocities v1,v2, CFO penalty is
`2*(v1-v2)^2 / [2*150^2*(1/a^2+1/b^2+1/(ab))+(20*(a+b)/2)^2]`, matching the
original graph's measurement/acceleration scales. The epoch+CFO control adds the
identical expression with sigma3samples and acceleration20samples/s². These
engineering values are fixed before path outcomes and not tuned by labels/GPS.
Linear epoch drift is allowed; zero epoch velocity is not preferred.

Phase edges also use nearest circular increments. Additional phase windings
are excluded by this model, not physically identified: every retained interval
exports this limitation, elapsed time and inferred circular drift; intervals
within10% of the phase branch boundary are marked. This is not a calibrated
sample-clock model or a guarantee of source identity at crossings.

Retain at most TWO positive-score RF path hypotheses per lane, each with≥8points
and≥6s span. This is a capacity limit, not an inferred source count. Extraction is
greedy candidate-exclusive path packing: a candidate belongs to at most one path,
each path uses at most one candidate per receiver-window. Different paths may use
different correlated alternatives from the SAME window. Report both candidate
hypothesis count and UNION receiver-window/physical-acquisition coverage; never
add paths as independent measurements. Keep skipped windows, unselected candidates,
shared-window counts and competing terminal-state scores. Neither cost nor the
reported terminal alternatives is a calibrated posterior or a global flow optimum.

Apply the unchanged actual graph port/configuration SEPARATELY to each selected
RF path as a quality diagnostic. It may reject/reduce supports; no graph growth
across paths and no joint satellite likelihood. Original winners form one input
stream. Preserve native observation IDs and all residual/quality flags. These
16-visit lanes cannot yield a≥20point quality-qualified piece: insufficient support
must remain explicit. Assigned is not accepted; two paths can estimate ONE source.

Truth evaluation is saved-only after RF seal: both continuous CFO distances and
epoch distances, unique-near-A/B/ambiguous/unmatched450Hz labels, path mixtures,
all-peak source coverage, missing windows and shared-window overlap. Proximity
does not prove source ownership. It must not select nodes, costs, aliases, path
counts or a favorable method. The recorded-port application remains a separately
frozen follow-on; this run uses only the four original synthetic sequences.

Preparation performs actual loaded-row→winner→original-graph parity on all four
contexts, plus owned invariants: counter/origin and whole-period translations,
large integer counters, crossings, gaps/empty windows, aliases, linear phase drift,
gate/rank ties, candidate exclusivity and per-path one-window ownership.
An initial pure crossing fixture incorrectly required the symmetric source-A path
to be output first; both pure paths were present. The test now checks deterministic
output and two distinct pure paths without imposing arbitrary source-name order.
The failed log is preserved and2seconds conservatively charged, no selector change.
Freeze all sources/settings/inputs before selection, then B exact preflight.
Run once, single worker/BLAS1,≤300 cumulative numerical seconds including setup
and tests; all24 lane-method slots retained, no parameter changes/retries/cap growth.
Live stdout remains outside prototype/ to avoid a seal/log race.
