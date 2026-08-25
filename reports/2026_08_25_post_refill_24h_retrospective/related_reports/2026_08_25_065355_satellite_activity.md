# Four-receiver Doppler context with conditional activity replays for capture 065355

## Outcome

`cap-20260825T065355-ba3e4fb8857b` is the strongest dwell reviewed so
far for the proposed persistent, unknown-count satellite model. Four gap-free
receiver paths on two physical radios independently recover the same curved
Doppler evolution for roughly the first 41 seconds. A causal-catalogue review
ranks NORAD 62124 / STARLINK-32608 first over that interval. Separate one-
receiver, fixed-hypothesis replays recover model-legal runs at the expected
times while retaining every scheduled probe and charging misses through gaps
in the chosen radio branch.

On the main resolved component, the new exact two-hypothesis replay prefers one
shared NORAD 62124 state from 30.0 through 42.3 s and leaves the supplied NORAD
66596 transition hypothesis inactive. Thus the first global result favors
continuation, not the apparent branch-by-branch handoff near 41 s.

This is compelling evidence for a common orbital Starlink-like source and a
strong contemporaneous association with NORAD 62124. It is **not** a secure
spacecraft identification: a whole-catalogue UTC -300 s control still finds a
different constellation member with a similar rate-shape score, the replay is
conditioned on radio-only branches, and no payload was decoded.

The capture is also a particularly useful next-stage solver fixture. The first
source may give way to shorter transition and tail candidates, so a global model
must choose the number of satellites, allow overlapping hypotheses, enforce a
0.5 s minimum run independently for each satellite, and count a physical peak
at most once.

## Sealed physical evidence

All four paths are 60 s long and gap-free at 11.690312500 GHz. The Standard
products contain 38 dealiased branches and 7,577 observations with no branch or
observation truncation. The paired scientific report is complete and reports
31 alias-expanded associations. Its strongest cross-radio agreements include:

| overlap | receiver pair | absolute slope difference |
|---:|---|---:|
| 17.639 s | 5d4d RX0 / 19f2 RX0 | 0.133 Hz/s |
| 14.914 s | 5d4d RX0 / 19f2 RX0 | 2.508 Hz/s |
| 14.889 s | 5d4d RX1 / 19f2 RX1 | 5.291 Hz/s |

Known-pilot analysis found 161 qualified segments among 960 analyzed segments.
The RX0 inventories are complete; the two RX1 inventories are explicitly
bounded by their per-path track-analysis caps.

The independently recovered rate evolution is approximately -3568 Hz/s early,
-3560 Hz/s in the middle, -3300 Hz/s around 32--41 s, -3160 Hz/s through the
41--43 s transition, and -3650 Hz/s in the tail. The repeated change in rate is
more discriminating than agreement on a single straight-line slope.

## Causal TLE association

The review used the causal 10,972-object snapshot with SHA-256
`ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee`
and the external Sausalito observer preset. Across 15 strict contiguous pieces
from the first three receiver paths, NORAD 62124 had joint chronological
train/holdout rate RMS of 28.5/46.2 Hz/s. The contemporaneous runner-up was much
worse at 220.0/217.9 Hz/s. The fourth path independently ranked NORAD 62124
first on each retained piece through 41.75 s.

The important control is less decisive: after shifting the entire catalogue by
-300 s, another constellation member scored 42.8/56.2 Hz/s. That is evidence of
orbital-plane phase degeneracy, so the large contemporaneous gap should not be
translated into an identity probability.

Candidate handover hypotheses from the same causal review are:

- about 0--41.5 s: NORAD 62124 / STARLINK-32608;
- about 41.5--48 s: NORAD 66596 / STARLINK-35811;
- about 48--50 s: short, unresolved ambiguity involving NORAD 64770;
- about 50--60 s: NORAD 69249 / STARLINK-37398.

These are candidate inputs for the joint optimizer, not accepted assignments.

## Conditional fixed-hypothesis activity replay

The new replay command consumes one resolved dealiased branch at a time. It
keeps all 2,400 native scheduled probes, but exposes only that branch's retained
observations rather than the dwell's full 24,000-candidate scan inventory. All
2,400 scans in this dwell had detections; a replay miss is therefore a gap in
membership of the chosen branch, not a `no_result` scan. The command fits one
delay and one constant CFO offset on the chronological first 60% of branch
observations, then runs the exact five-cell semi-Markov decoder over 100 ms
activity cells. Each selected run is legal under the imposed 0.5 s floor; that
constraint is not independent proof of continuous physical transmission.

| branch role | supplied candidate | fitted delay | train / diagnostic-tail CFO RMS | model-active interval(s) | assignments / misses | total - conditional branch-clutter null |
|---|---|---:|---:|---|---:|---:|
| early | 62124 | +0.15 s | 95.9 / 233.4 Hz | 0.8--6.3, 6.7--14.2 s | 388 / 132 | -954.7 |
| middle | 62124 | +1.05 s | 123.5 / 185.5 Hz | 18.9--32.2 s | 461 / 71 | -1198.8 |
| late-middle | 62124 | -0.70 s | 31.8 / 38.2 Hz | 32.3--41.0 s | 314 / 34 | -1088.5 |
| transition | 66596 | +0.20 s | 32.1 / 100.3 Hz | 40.8--42.3 s | 44 / 16 | -126.6 |
| tail | 69249 | -1.20 s | 159.3 / 157.3 Hz | 56.0--56.8, 57.8--58.5, 58.8--60.0 s | 52 / 56 | -38.8 |

Only the early-branch delay is not marked prior-dominated. On the shorter or
locally straighter arcs, orbital delay and constant CFO offset remain strongly
confounded. The fitted delay values should therefore not be reported as timing
measurements. The late-middle branch has the cleanest diagnostic-tail CFO-curve
result; the tail result is weak and fragmented under these provisional costs.

The diagnostic tail does not provide independent validation: the branch and
NORAD hypotheses were chosen with wider/full-dwell evidence. Profiling is also
staged before activity decoding and sees every observation in the supplied
branch, including observations the decoder later leaves unexplained. Exactness
applies only to activity and assignment after the branch, NORAD, delay, and CFO
offset have been fixed.

The structural result is more important than the absolute objective values:
the decoder can maintain a latent 100 ms activity state through missed 20 ms
probes, rejects sub-0.5 s internal islands, and pays the satellite cost once
while paying an episode cost for each maximal run. The numerical costs are
illustrative rather than calibrated likelihoods (`p_D=0.75`, clutter cost 4,
satellite cost 5.25, episode cost 5.75, CFO scale 100 Hz), so objective deltas
are not posterior odds and their magnitudes must not be compared across rows as
evidence strength. The tail interval ending at 60.0 s reaches the capture edge;
it does not demonstrate a physical shutoff there.

## Joint resolved-component replay

The bounded exact joint solver and its component-wide adapter are now working.
Unlike the rows above, this replay pools all seven branches in the main
resolved CFO component, deduplicates by source-observation ID, and gives the
two supplied satellite hypotheses one globally exclusive view of the same
evidence. The half-open 30--45 s window contains 600 scheduled probes and 457
deduplicated component observations, with no declared candidate truncation.

Before the joint replay, the shared NORAD 62124 nuisance pair was profiled on
the component observations from 30--40 s only (374 observations). A -2 to +2 s
delay grid at 0.05 s spacing, `N(0, 0.5^2)` delay prior, 100 Hz scale, and one
robust constant CFO offset gave the same data-only and posterior optimum:

- delay: -0.60 s;
- component CFO offset: -14,996.03 Hz;
- the profile was neither flat, ambiguous, nor prior-dominated;
- on the withheld-from-parameter-fit 40--42.3 s component tail, RMS was
  36.05 Hz over 77 observations, with median residual -14.34 Hz. This is a
  diagnostic tail, not independent validation of the preselected component or
  NORAD candidate.

The supplied competitor was NORAD 66596 with the prior-regularized transition-
branch pair (+0.20 s, -182,330.46 Hz). The exact two-hypothesis result was:

| supplied candidate | selected | model-active interval | assignments / misses |
|---|---|---|---:|
| 62124 / STARLINK-32608 | yes | 30.0--42.3 s | 451 / 41 |
| 66596 / STARLINK-35811 | no | — | 0 / 0 |

The joint total was 277.945 versus a component-clutter null of 1,828.0, or
-1,550.055 under the provisional costs. This does **not** establish NORAD
62124's identity, but it does not support the tempting branch-by-branch handoff
story inside this supplied component/candidate set: once one shared 62124
delay/CFO pair and global peak ownership are enforced, adding 66596 is not
useful through 42.3 s.

Nuisance sensitivity is scientifically important. Substituting the late-
middle branch's posterior or data-only 62124 pair still selected only 62124.
Substituting the early- or middle-branch pair instead produced an artificial
two-satellite split near 40 s. In contrast, with the component-profiled pair,
the one-satellite result was unchanged over CFO scales from 50 to 250 Hz and
from zero structural penalties through satellite/episode costs of 20/10. This
is why delay/CFO states must be shared and selected over the component-wide
evidence rather than fitted independently per radio branch.

This remains a conditional oracle result. The component and two catalogue
objects were supplied in advance, parameter profiling is staged rather than
joint with activity, source-observation IDs are the provisional physical-
exclusion groups, costs are uncalibrated, candidate-local epochs are
approximated by scheduled probe starts (maximum offset 1.19 ms here), and the
tool makes no catalogue-search, handoff, activity-probability, payload, or
spacecraft-identification claim.

## What this changes in the prototype plan

The single-satellite machinery is now adequate as an exact fixed-hypothesis
activity-DP kernel and replay diagnostic. The new factorial reference solver
adds exact joint assignment for two or three supplied hypotheses:

- branches within one resolved component share a legal CFO gauge, but separate
  branch replays currently fragment the approximately 0--41 s source;
- the three NORAD 62124 replays use three independently profiled delay/CFO pairs
  and cannot be merged into one persistent-satellite result;
- it prevents independent winners from claiming the same physical peak;
- it allows simultaneous satellites to consume distinct peaks from one native
  probe;
- it counts clutter once globally, charges the satellite-count penalty once per
  selected catalogue object, and charges each maximal episode separately;
- it independently recomputes the complete objective and refuses declared
  candidate truncation;
- delay/CFO profiles and near-optimal identity alternatives must remain visible.

The remaining solver gap is parameter-state selection at scale. The next slice
should accept a small bank of delay/CFO states per catalogue object, retain at
most one state for each selected object across all of its episodes, and compare
that result against this exact oracle. It then needs component-gauge nuisances,
per-cell visibility, near-optimal alternatives, and null-calibrated satellite/
episode penalties before a catalogue-scale MILP or column-generation backend
is warranted.

## Reproduce

The duration adapter input was generated from the sealed 5d4d RX0 Standard
root:

```bash
.venv/bin/python tools/evaluate_duration_constrained_satellite_assignment.py \
  --recording-manifest /srv/bulk/leo/recordings/2026/08/25/cap-20260825T065355-ba3e4fb8857b/manifest.json \
  --scientific-root /srv/bulk/leo/analysis/cap-20260825T065355-ba3e4fb8857b/capture-fec2f268eb324168853828203b6f72fd/scientific/path-standard/sha256:b40185ace0929be215411a24ac95641e3dc53fecf7d6a1a00ba8eb9b8c522bd2 \
  --session-id cap-20260825T065355-ba3e4fb8857b \
  --stream-id stream-0 --radio-id radio_pluto_5d4d --receiver-id 0 \
  --expected-sky-frequency-hz 11690312500 \
  --minimum-duration-s 0.5 \
  --output reports/figures/2026_08_25_065355_satellite_activity/capture-input.json
```

Example replay for the clean late-middle branch:

```bash
.venv/bin/python tools/replay_single_satellite_activity.py \
  --input reports/figures/2026_08_25_065355_satellite_activity/capture-input.json \
  --tle /home/mouse9911/.codex/visualizations/2026/08/22/01a02af8-cec4-7703-a883-75760f132c40/radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle \
  --tle-sha256 ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee \
  --catalog-number 62124 \
  --branch-id sha256:a976d32a217d5fdf487e231dc038d323da164719f8bad98463b0b4191108817d \
  --observer-latitude-deg 37.858988 --observer-longitude-deg -122.478103 \
  --observer-altitude-m -29 --observer-label spinnaker-sausalito \
  --cfo-sigma-hz 100 \
  --output reports/figures/2026_08_25_065355_satellite_activity/late-middle-62124.json
```

Joint replay using the component-profiled 62124 state:

```bash
.venv/bin/python tools/replay_joint_fixed_satellite_activity.py \
  --input reports/figures/2026_08_25_065355_satellite_activity/capture-input.json \
  --component-id sha256:944b71f491181440bed05f2317b62fd5482d505a13fdc384d89c4d68ceec47b3 \
  --start-s 30 --end-s 45 \
  --tle /home/mouse9911/.codex/visualizations/2026/08/22/01a02af8-cec4-7703-a883-75760f132c40/radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle \
  --tle-sha256 ac36512e603e6a21bc2ca16d0512a1e14db846ccbad9409d9ac601b371f16dee \
  --hypothesis 62124,-0.6,-14996.02513418381,0.72 \
  --hypothesis 66596,0.2,-182330.45990391474,0.08 \
  --observer-latitude-deg 37.858988 --observer-longitude-deg -122.478103 \
  --observer-altitude-m -29 --observer-label spinnaker-sausalito \
  --cfo-sigma-hz 100 \
  --output reports/figures/2026_08_25_065355_satellite_activity/joint-main-component-30-45-profiled62124.json
```

Machine-readable branch replays are in
`reports/figures/2026_08_25_065355_satellite_activity/`. Every output is marked
`candidate_only=true`, `specificity_claimed=false`,
`conditional_on_dealiased_branch=true`, `costs_calibrated=false`, and
`payload_decoded=false`.

The joint artifact additionally declares
`conditional_on_resolved_component=true`,
`conditional_on_explicit_fixed_hypotheses=true`,
`catalogue_search_performed=false`, `unknown_satellite_count_solved=false`, and
`handover_claimed=false`.

The reproduction recipe uses a locally frozen TLE file and an external observer
preset. The replay verifies the TLE bytes and positive element age but does not
itself bind snapshot acquisition provenance or observer coordinates to the
capture.
