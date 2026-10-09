# Active continuation: full cohort jobs are live

The unlimited below-1km goal is active and unachieved. This turn made progress:
qualified the three-region assembly, froze all148 comparison, launched it, and
resolved the DS18 common-bank ranking diagnostic at timing sigma1. No production
or RF collection changed.

Worktree: `/home/mouse9911/gits/leo-hard60-default`, branch `codex/hard60-default`.
Keep the user's original dirty checkout and unrelated untracked files intact.

## Live scientific jobs: poll, do not restart

- Uniform DS16 policy: exec `40092`, Python PID `4001824`, all DS16 inventory
  labels in order except DS16-056 (already completed as input smoke check).
- Uniform DS17 policy: exec `53710`, Python PID `4001840`, all DS17 except
  DS17-008 (already completed as input smoke check).
- Uniform DS18 policy: exec `18770`, Python PID `4001893`, all DS18 except
  DS18-009 (already completed as input smoke check).
- Original-policy baseline/completion lane: exec `73048`, Python PID `3985160`;
  currently finishing DS16-047 then DS16-055.
- Original-policy setup-retry lane: exec `58997`, Python PID `3985901`;
  currently finishing DS16-042.

Use current processes and result receipts as authority. Observation timeouts are
not terminal. Completed handles: original lane2 `86438`; assembly checks `54157`
and `79190`; uniform input smoke checks `78339` and `59886`; sigma1 diagnostic
`69092`. Do not invoke complete result labels again; immutable first results
raise FileExistsError. Pending-baseline labels write pending/ rather than final
results and may be resumed after the prerequisite completes.

The initial iteration51 publication is a partial snapshot (29/148 at rendering:
DS16 10, DS17 9, DS18 10). All were unchanged against prior candidate at that
checkpoint. Re-run summarize.py as results arrive. It retains all148 members,
dataset-specific baseline/previous/new metrics, matched c arms, RMS separately,
paired regressions and failed/pending/unstarted coverage. Additional regional
fits increase compute; no equal-total-compute claim is allowed.

Iteration45's original-policy comparison is 60/63 DS16, 51/51 DS17, 34/34 DS18
at this checkpoint. Re-run its summarize_completion.py and publish its final
full-membership report once the remaining three members complete. Preserve all
seven original setup failures and their separate retry receipts.

## Frozen implementations and findings

Iteration50: new region_pipeline.py differs from iteration20 only in initial
region selection. Selection order baseline, sep25, sep50; added candidates must
converge and beat score, earlier wins ties; arms chosen independently. The same
fitted-region bank/calibration/seed is shared downstream. Four numerical controls
matched frozen vectors/clocks/scores/errors to1e-5, two selection tests pass.

Iteration51 protocol covers63+51+34=148. Some old cases never had sep25; compute
missing sep25 and add sep50 uniformly. Archived regional docs are bound to exact
inputs/configuration/grid. Completed-baseline receipts for pending members are
allowed to arrive later but must bind frozen recording digests. DS16-046 reuses
its already consumed iteration48 sep50 result openly. This is descriptive consumed
research, not fresh validation. Executed numerical source and protocol stay immutable.

Iteration52: common145 satellite bank/shared clock frame, same four ordinary/
recovered source-arm starts and 20s600 budget as46, but relative timing sigma1.
Seven of8 fits converge. Recovered wins both arms: fitted-c1.151112km with score
29246.614825 versus best converged ordinary30043.634481; zero-c1.930915km with
score29498.895275 versus ordinary30102.632796. One ordinary fitted fit remains
nonstationary. All c0 locks and prediction/transport/penalty audits pass.
This is NOT a benchmark replacement: recovered starts still came from the old
consumed diagnostic sequence. All dataset means retain the operational failure.

## Next scientific action

Remove the recovered-seed dependency. First census transports from all saved
ordinary regional starts in iteration41's32 successful regions, on its common145
bank with the shared ordinary calibration and sigma1. Keep association,
zero-timing and own-continuation starts from both source arms; exact duplicate
physical seeds can be deduplicated without using position error. Verify physical
predictions, padded relative timing and clock null bases; report infeasible
shared-frame seeds instead of silently clipping them. Preserve every region's
coverage/failures. Then refit matched c arms with a frozen equal budget per start,
selecting converged common-model scores across regions. The original inventory
is reference-free but its budget was developed on consumed data; don't call it
unseen validation. Reference coordinates only enter post-inference diagnostics.

Iteration49 found all4 failed fitted-c endpoints at hard horizon visibility
transitions; four converged c0 controls showed no flips at1e-4 scaled steps.
Smooth above-horizon detection remains another candidate, but requires both
signal-mixture and no-detection-normalization derivatives and gradient tests.
Sigma1 already resolves ranking in the controlled branch test, so prioritize
reference-free initialization before adding another model change.

Keep published contracts, scientific fixtures, fitted-c production default,
bounded recovery and longest16 per-track PNGs unchanged. No new RF collection.
