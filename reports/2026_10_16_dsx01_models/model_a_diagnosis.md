# DSX-A primary endpoint diagnosis

Read-only analysis of all five saved `full-fitted-c` original/A endpoint pairs.
No optimizer was run and the frozen implementation, dataset and matched
evaluation were not changed. This is a development diagnosis; the completed
temporal and matched c=0 results retain their separate interpretation in the
parent comparison. Its 125 matched receipts completed without execution failure;
that completion is distinct from endpoint convergence.

## Complete primary comparison

| Source | Full associations, original → A | Challenge associations | Outside new / lost | Outside retained identity changes | Full intersection RMS, original → A (Hz) |
|---|---:|---:|---:|---:|---:|
| S01 | 1643 → 1815 | 14 → 76 | 298 / 188 | 105 | 158.800 → 159.151 |
| S02 | 1657 → 1729 | 19 → 18 | 105 / 32 | 32 | 167.920 → 166.365 |
| S03 | 3091 → 3360 | 28 → 94 | 211 / 8 | 107 | 142.309 → 138.590 |
| S04 | 2381 → 2414 | 25 → 27 | 43 / 12 | 24 | 158.705 → 158.212 |
| S05 | 2450 → 2562 | 10 → 38 | 115 / 31 | 42 | 169.764 → 169.921 |

Across all recordings, 932 assignments are new, 274 are lost, and 326 retained
points change selected satellite. Outside the challenge there are 772 new,
271 lost and 310 changed identities. The net full-scan increase is 658;
challenge assignments increase from 96 to 253. These are model classifications,
not verified satellite identities. S01 and S05 both worsen slightly on the
intersection RMS despite their net association gains.

## Loss mechanism: changed prediction dominates q alone

The association test is equivalent to
`max_k odds(q_k * visibility_ik) * Gaussian(residual_ik) > clutter_rate / ALIAS_HZ`.
The common posterior denominator cancels. A competing satellite alone cannot
turn an associated row into an unassociated row. It can change its selected
identity; losses require the maximum signal density to cross clutter.

Two diagnostic interventions classify each actually lost row: change q alone
while retaining all original residuals/visibility, or change residuals/visibility
while retaining original q. These are read-only interventions, not additional
fitted arms. The prediction intervention includes geometry, timing, calibration
and smooth visibility together; it does not isolate timing mathematically.

| Source | Outside lost | Only prediction change sufficient | Either intervention alone sufficient | Both changes needed | Only q change sufficient |
|---|---:|---:|---:|---:|---:|
| S01 | 188 | 181 | 3 | 4 | 0 |
| S02 | 32 | 31 | 0 | 1 | 0 |
| S03 | 8 | 6 | 2 | 0 | 0 |
| S04 | 12 | 10 | 0 | 2 | 0 |
| S05 | 31 | 26 | 2 | 3 | 0 |
| Total | 271 | 254 | 7 | 10 | 0 |

Thus 261/271 outside losses persist with original q and new predictions. Seven
persist with new q and original predictions. q participates in ten further
losses that neither intervention causes alone. The shared q budget stays 1.6
at both endpoints in every recording. This does not make q harmless: it changes
thresholds and winner identities, but simple q starvation is not the dominant
cause of these lost assignments.

S01 is the clearest timing reassignment. Its lost rows' median absolute residual
against their formerly selected satellite rises from 164.8 to 2757.5 Hz.
Receiver calibration changes by a median 25.7 Hz, maximum 112.5 Hz, and position
moves 0.202 km. Large per-satellite timing changes therefore provide strong
evidence for the dominant mechanism, although the intervention does not isolate
them from every other parameter:

* Satellite 51117 loses 55 outside rows and switches 15 more away, accounting for
  all 70 of its original assignments. Total timing moves −14.550 → −1.182 s;
  q moves 0.06790 → 0.03954. It ends with 43 assignments to different support.
* Satellite 62052 loses 51 outside rows despite q increasing 0.06193 → 0.06852.
  Timing moves −1.341 → −2.014 s. Its lost rows' old-satellite median residual
  rises from 121.3 to 2500.9 Hz.
* Satellite 67954 loses 25 outside rows but gains 67 outside rows. Timing moves
  −1.269 → −2.475 s and q more than doubles, 0.03428 → 0.07512.
* Satellite 56413 loses 14 outside rows and gains 106. Timing moves
  5.433 → 1.993 s; q moves 0.01913 → 0.10243.

Other recordings show the same replacement pattern with fewer losses. In S02,
55282 loses ten outside rows while gaining 66, and 68711 loses six while gaining
21; their total timing changes are −6.485 and −21.810 s. In S04, 68021 loses
three outside rows and gains 40 after an −8.608 s timing change. In S05, 58362
loses 12 outside rows and switches away its one other original assignment, but
ends with 162 assignments, after timing 4.145 → −1.287 s and q
0.01379 → 0.09749. These examples explain numerical replacement, not which
identity was correct. All eligible satellite rows, including zero-loss rows,
are retained in `model_a_diagnosis.json`.

The small S05 intersection deterioration is present even among the 2373 retained
rows whose selected identity stays the same: RMS 169.585 → 169.849 Hz. Its 46
changed-identity retained rows improve 178.775 → 173.595 Hz. Calibration drift
(median absolute change 39.7 Hz, maximum 66.5 Hz), small timing movements and
the point-mixture tradeoff can therefore degrade stable support even while a
rescued arc improves the global objective. S01 stable-identity retained RMS
also worsens, 157.848 → 158.036 Hz.

## Convergence and audit domains

| Source | A physical projected KKT | A clock projected gradient maximum | A q projected gradient maximum |
|---|---:|---:|---:|
| S01 | 474.018 | 7.027 | 3.349 |
| S02 | 205.491 | 1.534 | 1.122 |
| S03 | 1206.112 | 9.649 | 15.885 |
| S04 | 521.554 | 1.800 | 2.057 |
| S05 | 304.038 | 7.652 | 1.700 |

All A endpoints are feasible research iterates and all fail the 0.001 strict
KKT threshold. The physical gradient dominates, while clocks and q are also
unfinished. Every A run exhausts its 180-evaluation allowance, so lower objective
does not establish convergence. The q-only proposal polishing allowance also
does not certify an optimized q block.

All five saved original endpoints passed their production replay audit using
their recorded 25 km local disk. The shared research audit uses the broad
regional disk without that local disk. Under the latter audit S02 alone fails
(9.98687), despite passing its production audit (0.000914501). Its original
position lies exactly 25.000000000008 km from the recorded local center, so
removing an active constraint changes stationarity. The A S02 position is
25.694 km from that center; the continuation is 25.725 km away. The broader
audit's 4/5 original count must not be described as four production-valid seeds.
These are different feasible direction sets, not contradictory replay results.

Common timing is also a gauge summary: it changes by less than 0.615 s on every
recording while individual total timings can move by more than 20 s. Relative
timing RMS decreases in all five recordings. A blanket stronger prior toward
zero is therefore not a demonstrated remedy for loss of established support.
Position movement is 0.067–0.703 km; none of this establishes localization
accuracy or improvement relative to an independently surveyed location.

## Next bounded iteration, after the matched evaluation

1. Keep this version frozen. Read the complete held-prediction and c=0 comparison
   before choosing any new settings; evaluate losses and gains over every
   recording, channel and full denominator.
2. Fix proposal ranking before changing the scientific likelihood: the current
   proposal sum includes only positive arc gains. It does not debit arcs harmed
   by the same satellite timing. Rank signed gains over automatic old and new
   coherent arcs, deduplicate overlapping evidence, and test a proposed timing
   against all training support for that satellite across channels. Retain
   multiple physical timing hypotheses through bounded whole-objective scoring
   rather than committing solely to each candidate's best positive arc gain.
3. Use a predeclared direct-total-timing trust region around each proposal during
   recovery and alternate bounded timing/calibration and q updates, with a shared
   evaluation counter. Reserve enough evaluations for a final joint stationarity
   check. Physical-gradient convergence is the current largest numerical deficit;
   q-only recovery alone cannot resolve it. Report a failed convergence gate
   honestly if the fixed allowance remains insufficient.
4. Add a training-only coherent-support regression diagnostic to proposal
   acceptance. Retain the original objective and classification for comparison;
   any hard retention constraint, extra timing/q prior, or altered likelihood
   must be a separately declared research arm. Protect coherent evidence rather
   than blindly locking every original point identity, since original labels
   can themselves be wrong. Recheck both temporal directions and matched c=0
   with the same new policy and budget.

The justified next step is better balanced proposal evidence and bounded
convergence recovery, followed by excluded-data testing. Association gains alone
do not authorize production promotion or a claim of improved satellite identity
or position accuracy.

The completed comparison provides a further limit: cold held association is
about 12% across methods, and A exceeds continuation by only about 0.28 percentage
points early-to-late and 0.44 points in reverse. All cold endpoints remain
nonstationary. These small candidate-conditioned changes do not validate the
large warm-start in-sample gain. All 12 established C07 assignments are retained
by A in the primary comparison; this specific retention does not erase the
other outside-window losses tabulated above.
