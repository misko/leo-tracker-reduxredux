# Structural-penalty calibration corpus

This directory freezes the empirical analyzer-null study for the duration-constrained
Starlink activity prototype. It is a 15-cluster tuning / 59-cluster locked-holdout
design. No catalogue replay or holdout adjudication was performed while constructing
the census, duration inputs, corpus specification, or plan.

## Frozen identities

- Study: `raw-satellite-activity-structural-penalty-20260825-cap10-v1`
- Census cutoff: `[2026-08-21T00:00:00Z, 2026-08-25T12:15:00Z)`
- Census SHA-256:
  `sha256:6edc96ab86115ccafe95f6ca2879f065ab57d920a9c6a35e234af552bf428f12`
- Corpus specification SHA-256:
  `sha256:aff5d9af531f140b2de6e8147c5f67a9e4458b48f9b0f4b9a84413646291f0c5`
- Frozen study plan SHA-256:
  `sha256:f9deb0ede7885aa9e19ead2252a9aae1d48bdd3fbbf738a74d95b28521c38cdd`
- Controlled non-source search-family SHA-256:
  `sha256:dd3310bd3aaeaa43e7a5a625b6582df2d537c9ea9a5b501669bf34ca447ee678`
- Producer implementation manifest SHA-256 at freeze time:
  `sha256:2fc24aa878a21ff693b9d6a2e1cfda8bf22946c47d1a2e46ada7f5bf363fcba1`

The producer manifest includes the transitive contract serialization surface,
including both `src/leo/contracts/base.py` and `src/leo/contracts/digests.py`.

The plan stores resolved calibration, TLE, and duration-dataset paths for execution.
Paths are locators, not controlled-family identity: the runner hashes the bytes against
their frozen digests and independently recomputes every full search-configuration digest
before replay.

## Census and split accounting

The census read 495 sealed Standard analysis manifests. There were 258 candidate
`no_result` path members before eligibility filtering. The fixed family requires a full
60 s, 150,000,000-sample, 2.5 Msps recording; exactly 2,400 scheduled probes; ten source
and retained candidates per probe; gap-free coverage 1.0; PilotScanV3 GLRT64-compatible
configuration; final-bank and path-report `no_result`; and zero schedule, candidate,
observation, and trajectory truncation.

Pre-eligibility exclusions were 97 members missing dealiased bank, final bank, and frame
segments, plus 33 members missing dealiased bank and frame segments. Entire sessions
appearing anywhere in score-calibration-v3 sources were then excluded:

- `cap-20260824T124902-20c1bfc10f52`
- `cap-20260824T193733-1454b499b8bb`
- `cap-20260825T065355-ba3e4fb8857b`

That calibration-source rule removed eight otherwise-eligible members. The resulting
homogeneous universe is exactly 74 session clusters / 120 path members. Cluster sizes
are 43 single-member, 20 two-member, seven three-member, and four four-member clusters.
The tuning split has 15 clusters / 27 members; holdout has 59 clusters / 93 members;
there are no unused clusters.

Every compatible session whose structural evidence had already been inspected was
forced into tuning:

- `cap-20260823T022003-6aeb95ddead5`
- `cap-20260825T022509-735366370195`
- `cap-20260825T024108-b84b64ae03dd`
- `cap-20260825T062228-886fe2dd9cde`
- `cap-20260825T063754-ef4ff74230d6`
- `cap-20260825T082057-aa0a740de6db`
- `cap-20260825T082330-c8a2692839cd`
- `cap-20260825T084200-6614872688fa`
- `cap-20260825T085857-6d87a16d291d`
- `cap-20260825T091429-c1446df4dd6a`
- `cap-20260825T101702-f60463e1402e`
- `cap-20260825T105640-facdadeffb3b`
- `cap-20260825T105915-2770b84587cc`
- `cap-20260825T111222-a2d4ce2afb9a`

The remaining tuning slot was selected by ascending
`SHA256(study_id + NUL + session_id)`: `cap-20260824T053636-5f655fed330a`.
Every other eligible cluster went to holdout without inspecting its structural replay.
The discussed `cap-20260825T071811-863ec02af098` dwell was ineligible because it has no
sealed Standard `capture-*` analysis member satisfying this contract.

The 022003 member is the sole narrow protocol exception. Its scan, schedule, alias map,
dealiased bank, final bank, and path report establish a complete empty `no_result` raw
inventory with zero truncation, but the older sealed run predates
`standard.pilot-doppler-segments.v1.json`. Its duration input explicitly persists
`frame_evidence_available=false`, the missing-product reason,
`raw_activity_inventory_complete=true`, zero canonical observations, and no known-pilot
claim. The fail-closed extractor accepts this only through its explicit opt-in, and the
exception remains in tuning.

## Ordered penalty path

The componentwise-monotone path is:

1. `(satellite_cost=5.25, episode_cost=5.75)`
2. `(6.25, 6.75)`
3. `(8.25, 8.75)`
4. `(10.25, 10.75)`
5. `(14.25, 14.75)`
6. `(22.25, 22.75)`

The current prototype pair is first. Costs near six are the log-count scale for roughly
440 visible catalogues and 600 possible 0.1 s episode starts. Later pairs add a
conservative monotone safety margin, ending at combined cost 45 for hard 0.5 s clutter
bursts.

## Final preparation and preflight

The final materialization and freeze used:

```bash
.venv/bin/pytest -q tests/analysis/test_duration_constrained_satellite_assignment_tool.py
.venv/bin/python reports/figures/2026_08_25_structural_penalty_calibration/prepare_structural_penalty_corpus.py --output-root reports/figures/2026_08_25_structural_penalty_calibration
.venv/bin/python tools/freeze_raw_satellite_activity_structural_penalty_plan.py --corpus-specification reports/figures/2026_08_25_structural_penalty_calibration/structural-penalty-corpus-specification.json --corpus-specification-sha256 sha256:aff5d9af531f140b2de6e8147c5f67a9e4458b48f9b0f4b9a84413646291f0c5 --output reports/figures/2026_08_25_structural_penalty_calibration/structural-penalty-study-plan.json
```

A tuning-only dry preflight re-opened and hashed 27 duration inputs and recomputed all
162 member-by-pair search digests. All passed. It did not invoke catalogue replay, open
holdout duration inputs, or inspect holdout screen evidence.

After review of the freeze, tuning evidence was generated deterministically with:

```bash
/usr/bin/time -p .venv/bin/python tools/run_raw_satellite_activity_structural_penalty_study.py --plan reports/figures/2026_08_25_structural_penalty_calibration/structural-penalty-study-plan.json --plan-sha256 sha256:f9deb0ede7885aa9e19ead2252a9aae1d48bdd3fbbf738a74d95b28521c38cdd --split tuning --output-root reports/figures/2026_08_25_structural_penalty_calibration/tuning-evidence
```

The runner consumes the frozen split rather than rediscovering sources, validates every
replay through the adjudicator, and emits a complete relocatable evidence index. Holdout
execution is refused unless both a canonical immutable tuning lock and its digest are
supplied; it then evaluates only the locked pair.

## Tuning result and immutable lock

The 162 tuning member-by-pair evaluations completed in 133.25 s wall time. The complete
evidence index is `tuning-evidence/tuning-evidence-index.json`, SHA-256
`sha256:6f42c729d0232e12f18e4a48c7aa83a89949c92ba8352a66792512723400825f`.
It contains 27 entries for each of the six pairs, uses only relative tuning replay paths,
and has `lock_digest=null` as required.

The immutable lock was produced in 0.21 s with:

```bash
/usr/bin/time -p .venv/bin/python tools/calibrate_raw_satellite_activity_structural_penalties.py lock --plan reports/figures/2026_08_25_structural_penalty_calibration/structural-penalty-study-plan.json --plan-sha256 sha256:f9deb0ede7885aa9e19ead2252a9aae1d48bdd3fbbf738a74d95b28521c38cdd --evidence-index reports/figures/2026_08_25_structural_penalty_calibration/tuning-evidence/tuning-evidence-index.json --evidence-index-sha256 sha256:6f42c729d0232e12f18e4a48c7aa83a89949c92ba8352a66792512723400825f --output reports/figures/2026_08_25_structural_penalty_calibration/tuning-evidence/structural-penalty-lock.json
```

All six ordered pairs had 15 certified-null clusters, zero false activations, and zero
inconclusives. The declared first-eligible rule therefore selected pair 0,
`(satellite_cost=5.25, episode_cost=5.75)`. The lock is
`tuning-evidence/structural-penalty-lock.json`, SHA-256
`sha256:a2d9ea13afc0b644d462ab17ea9ae739234be612ab8325658c21a73120e9d594`.
A separate canonical recomputation matched the lock bytes exactly. No holdout duration
input, screen evidence, or adjudication was opened during tuning or locking.

## Locked holdout qualification

After independent review released the holdout, the runner evaluated all 93 predeclared
holdout members at locked pair 0 only. The first attempt stopped fail-closed after 66
persisted members when the first full-screen branch exposed a verifier mismatch: the
frozen producer correctly stores its elided clutter constant under
`raw_inventory.dominated_weak_candidate_elision`, while the adjudicator had read only the
certified-null branch's top-level location. The rejected partial file was removed and no
later member was opened by that attempt.

The repair changed only the non-producer-bound adjudicator. It now reads the strict
schema-defined location for each result branch, rejects contradictory duplicate
locations, and continues to reconcile the value with the persisted decision objective.
No producer-manifest file, plan byte, search digest, penalty, split, or scientific result
changed. Focused tests and an independent audit passed before exact-output resumption.

The holdout command, run first fail-closed and then resumed with verified reuse, was:

```bash
/usr/bin/time -p .venv/bin/python tools/run_raw_satellite_activity_structural_penalty_study.py --plan reports/figures/2026_08_25_structural_penalty_calibration/structural-penalty-study-plan.json --plan-sha256 sha256:f9deb0ede7885aa9e19ead2252a9aae1d48bdd3fbbf738a74d95b28521c38cdd --split holdout --output-root reports/figures/2026_08_25_structural_penalty_calibration/holdout-evidence --lock reports/figures/2026_08_25_structural_penalty_calibration/tuning-evidence/structural-penalty-lock.json --lock-sha256 sha256:a2d9ea13afc0b644d462ab17ea9ae739234be612ab8325658c21a73120e9d594
```

The failed attempt used 266.90 s wall time. The successful resumed run used 445.51 s and
emitted `holdout-evidence/holdout-evidence-index.json`, SHA-256
`sha256:2324e2745bdc1cb276d7ffae81452ce11cc5e8228121a6d66e43f694998e4c6f`.
The index has exactly 93 entries, all at pair 0, and is bound to the immutable lock.

Qualification used:

```bash
/usr/bin/time -p .venv/bin/python tools/calibrate_raw_satellite_activity_structural_penalties.py qualify --plan reports/figures/2026_08_25_structural_penalty_calibration/structural-penalty-study-plan.json --plan-sha256 sha256:f9deb0ede7885aa9e19ead2252a9aae1d48bdd3fbbf738a74d95b28521c38cdd --lock reports/figures/2026_08_25_structural_penalty_calibration/tuning-evidence/structural-penalty-lock.json --lock-sha256 sha256:a2d9ea13afc0b644d462ab17ea9ae739234be612ab8325658c21a73120e9d594 --evidence-index reports/figures/2026_08_25_structural_penalty_calibration/holdout-evidence/holdout-evidence-index.json --evidence-index-sha256 sha256:2324e2745bdc1cb276d7ffae81452ce11cc5e8228121a6d66e43f694998e4c6f --output reports/figures/2026_08_25_structural_penalty_calibration/holdout-evidence/structural-penalty-qualification.json
```

The 0.23 s adjudication produced
`holdout-evidence/structural-penalty-qualification.json`, SHA-256
`sha256:86c7d56b47c10c82a3e3b4ba9b265954f457887ba094da0617da531e621ee564`.
Cluster accounting is 57 certified null, one false activation, and one inconclusive;
member accounting is 91 certified null, one activation, and one inconclusive. The full
per-cluster/member inventory is in the qualification JSON.

The false activation is `cap-20260824T133623-98176fbf1958`, member
`a6c8978165c0`: STARLINK-11242 / NORAD 60903, delay +0.6 s, CFO offset
+350588.7965920881 Hz, one uncensored 0.6 s episode over cells `[0,6)`, 16 assignments,
and objective delta -23.621640857596475. The inconclusive cluster is
`cap-20260824T144651-7599c1353b67`, member `98b068ab80ca`: its pruned catalogue search
selected nothing and therefore cannot certify the global null.

Because one cluster is inconclusive, the protocol withholds a completed-sample exact
upper bound. Even the best-case exact one-sided 95% Clopper-Pearson upper bound with one
false activation among all 59 clusters is 0.0778979215188183, above the fixed 0.05 gate.
Failure is therefore certain, and pair 0 is not qualified for the declared empirical-null
scope. An independent 0.27 s recomputation verified the plan, lock, index, qualification,
all 93 replay-file digests, every search configuration and objective classification, and
canonical qualification bytes.

## Post-qualification diagnosis

The protocol outcome above is immutable, but a read-only source audit shows that its
single “false activation” is not credible noise. The selected path was the weakest of
four simultaneous same-frequency receiver paths in the same capture. Over the first
0.6 s, all four paths contain an independently measured high-margin descending CFO
feature. Straight-line fits give slopes of -4681.5, -4780.1, -4752.6, and -4777.8 Hz/s
with 56.6--69.6 Hz RMS residuals. Three sibling path reports are `complete`; only the
evaluated member is `no_result`. The selected member contributes 16 unique detector-
resolution exclusion groups on 16 probes, so exact-duplicate basin reuse did not create
the event. Those groups are not claimed to identify distinct physical sources.

The cross-path audit used each path report's persisted `raw_report.initial_glrt64` rows,
kept `time_s <= 0.6` and `initial_margin >= 0.1`, and fit ordinary least-squares CFO
versus scheduled probe time. The recording manifest binds both streams to the same
11,440,312,498 Hz sky-frequency setting and their first-sample estimates differ by only
0.402 ms.

| Scope | Receiver path | Path status | Points | CFO rate (Hz/s) | Fit RMS (Hz) |
| --- | --- | --- | ---: | ---: | ---: |
| `4d0f7b21` | 19f2 / RX1 | `complete` | 25 | -4681.5 | 69.6 |
| `a6c89781` | 19f2 / RX0 | `no_result` | 17 | -4780.1 | 69.5 |
| `c6c20ba7` | 5d4d / RX1 | `complete` | 16 | -4752.6 | 64.0 |
| `cb023e81` | 5d4d / RX0 | `complete` | 25 | -4777.8 | 56.6 |

The final banks on 19f2/RX1 and 5d4d/RX1 then retain longer branches beginning at
0.675 s and 0.650 s and continuing to 5.700 s and 6.775 s, respectively. This is
additional evidence that the boundary burst is the beginning of real RF activity rather
than a detector-only fluctuation on the held-out path.

This means the locked model successfully recovered a real short common-RF feature that
the upstream path-level trajectory analyzer did not retain. It does **not** establish
NORAD 60903: the feature is only 0.6 s and nearly linear, the fine cost gap to the next
catalogue candidate is 6.825, all three shortlisted catalogues activate individually,
and several delay states are nearly tied. The frozen TLE snapshot was acquired after
this 2026-08-24 13:36 UTC capture, so this candidate association is retrospective rather
than a causal replay. The decoded run also begins at the capture boundary;
`left_censored=false` records disabled censoring in this replay, not an observed
physical turn-on.

The deeper flaw is the empirical-null definition. The frozen census admitted a path
when that path's final bank and path report were `no_result`, even if sibling paths in
the same capture were active. Rechecking the 74 frozen clusters shows that only four
clusters are capture-wide four-path `no_result` dwells; the other 70 contain at least
one `complete` or `partial_coverage` sibling path. Raising the structural penalties to
suppress this witness would therefore train away exactly the >=0.5 s intermittent
signals the model is intended to recover.

Future calibration must separate two questions:

1. **Signal-presence/cardinality calibration** uses capture-wide no-signal evidence,
   fixed-opportunity matched-sequence or detuned controls, and planted/semi-synthetic
   emitters. It calibrates N=0 versus activity and the satellite/episode penalties. A
   blind acquisition replay with a circularly rolled pilot is not a valid null: the
   timing-epoch search can absorb the symbol roll and reacquire the real pilot at a
   shifted epoch. Sequence controls must therefore compare hypotheses over the same
   timing/CFO opportunity set, or maximize both hypotheses symmetrically and interpret
   only their contrast.
2. **Catalogue-specificity calibration** uses real signal-bearing dwells with wrong-time
   or matched wrong-catalogue controls. It measures whether a short CFO curve identifies
   a particular TLE, rather than treating any orbital-looking activation as noise.

The `144651` inconclusive had a different cause. Its optimistic zero-residual lower
bound could construct a five-cell activation with delta -1.6028, while every evaluated
real TLE state remained off. The frozen producer refined only 32 of 484 tied coarse
catalogues, so its pruned N=0 result was not a finite-universe certificate.

A separate post-qualification diagnostic exhaustively evaluated all 484 full-window-
visible Starlinks over the complete declared 41-delay by two-CFO-mode bank: 39,688 exact
single-satellite states. Every catalogue minimum selected null with delta 0. By the
additive objective and global exclusion-group capacity, any feasible multi-satellite
schedule is a sum of disjoint single-satellite contributions; therefore no N can beat
null if every single-state minimum is nonnegative. The result is `bounded_exact_null`
for this finite model. Because all catalogue minima are null ties, their serialized
delay/CFO representatives and catalogue ordering are deterministic tie-breaks, not
evidence of relative closeness. It ran in 567.76 s and is stored outside the frozen
holdout at
`/home/mouse9911/.codex/visualizations/2026/08/25/01a036e6-81b5-7f91-83bf-c12b18268cb3/144651-bounded-null-vs-any.json`,
SHA-256
`40e756f96c9ba56dd836180694d217137f268dc8274e1d4bcd936353406d403b`.

This diagnostic resolves the earlier computational inconclusive, but it does not alter
the immutable failed qualification: the real `133623` activity witness remains, and the
original protocol was already spent. Exactness is conditional on the 484 full-window-
visible TLEs, discrete [-2,+2] s / 0.1 s delay grid, two data-proposed CFO modes per
delay, and acquisition-capped raw inventory. Rise/set objects and continuous nuisance
spaces remain outside the certificate; it is not an unrestricted astrophysical null.
The digest-bound TLE snapshot was collected after the capture, so this diagnostic is
also retrospective rather than a causal operational replay.
