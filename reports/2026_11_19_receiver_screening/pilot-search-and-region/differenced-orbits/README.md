# Staggered RF Doppler contrasts

The solver withheld on all **18 offers**. Nineteen anonymous three-carrier groups qualified on the training prefix across six real roof recordings. Two retained the same three arcs into held windows. Both remained ambiguous among causal orbit assignments. Five original offers produced forced coordinates, with errors of **6.84–24.70 km** against **8.19 km** for the tile centres. The displaced offers also withheld. [Support figure](staggered-support.png) · [Position charts](charts/README.md) · [Scores](scores.csv)

## Observations and clock model

The previous paired-Doppler experiment subtracted two CFO measurements from one exact window at one RF. This experiment uses three distinct actual RFs visited at staggered times by the same physical receiver and band. Across **77,286** native zero-offset visits, there were zero coincident different-RF windows on a common receiver/band path. Each carrier contributes a slope evaluated at the same window centre using its own bracketing native samples. The operator differentiates a local quadratic and applies the same weights to measured and modeled CFO. The two orthogonal between-carrier contrasts therefore remove an additive receiver clock term when it is quadratic within the eight-second window. [Protocol](PROTOCOL.md) · [Earlier exact-window pairs](../../receiver-choice/paired-doppler/README.md)

Each slope also removes its own constant carrier offset, fixed integer CFO alias and fixed RF calibration. The largest measured fixed-`c` design magnitude was **2.08 × 10⁻¹⁵ GHz/s**, at floating-point precision. A fitted-`c` arm is unavailable. Its coefficient is unidentified even across the distinct carriers. The original v5 reference retains both measured calibration arms. Independent RF-path terms remain a physical source of uncertainty. A second arbitrary clock slope proportional to RF reduces the two observable contrasts to one per window. One free clock slope per lane would absorb all three measurements. The largest pairwise cubic clock moment was **1.35 s²**. A common cubic CFO derivative therefore leaks into a pairwise rate contrast according to that moment. [Native stencil and orbit receipts](positions.jsonl.gz)

The observation-only tracker linked gated original peak alternatives. The early group selector rejected **130** proposed triples whose RF-normalized slopes could be copies of the same physical Doppler. Candidate tuples also require three different NORADs. On the prefix the search considered about **312,000–823,000** ordered combinations per fitted offer, including repeated tuples across the five screen points. It retained at most sixteen per group and scored exact forward geometry on the tiled lattice. Native counters, peak ranks, alias-lifted CFO and derivative weights are recorded for every modeled group. Prepared StarLoc beacon measurements have genuine simultaneous support on a single RF. That corpus can test common-clock geometry with the previously reported single-RF method. The distinct-carrier design here has six acquisitions at one surveyed roof. [Blind input seal](prediction-lock.json) · [Single-RF measured transfer](../../streamlined/measured-transfer/README.md)

## Geographic scores

Every endpoint below is a training-only forced position. All six original squares contained the survey coordinate. All displaced squares excluded it by at least **26.64 km** from the closest edge. The three queries per capture have identical native witnesses and time weights. The time sham uses the original square and advances only the orbital propagation UTC by 79 seconds.

| Recording | Early / held triplets | Original forced km | Displaced centre / forced km | Time-sham forced km |
| --- | ---: | ---: | ---: | ---: |
| DS26-0261 | 4 / 0 | 7.36 | 61.03 / 56.26 | 25.37 |
| DS29-0519 | 5 / 0 | 6.95 | 55.24 / 50.17 | 13.27 |
| DS26-0283 | 2 / 0 | 6.84 | 48.68 / 49.18 | 6.73 |
| DS26-0136 | 5 / 1 | 8.09 | 51.59 / 46.76 | 14.48 |
| DS26-0124 | 3 / 1 | 24.70 | 55.69 / 55.18 | 15.97 |
| DS29-0082 | 0 / 0 | — | 52.82 / — | — |

On the two exact known requests, original v5 produced errors of **1.39/1.36 km** for DS26-0261 and **0.25/0.32 km** for DS29-0519 in `c=0`/fitted order. Its absolute CFO RMS was **94.62/85.06 Hz** and **100.75/81.34 Hz** respectively. The new receiver measures rate-contrast RMS in Hz/s. Its four modest improvements over the original tile centre came from forced positions. DS26-0283's time sham was also slightly closer to survey than the original-time estimate. [Matched references and scores](scores.csv)

## Held orbit evidence

| Real original offer | Training winner | Held closest alternative | Training gap, Hz/s | Held RMS, Hz/s | Held RMS displaced / time sham, Hz/s | Held geographic lead, Hz/s |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| DS26-0136 | 47895 / 66801 / 58416 | 58067 / 54868 / 52674 | 0.25 | 61.29 | 63.17 / 144.73 | +2.28 |
| DS26-0124 | 48304 / 62554 / 47375 | 66086 / 59024 / 46076 | 0.84 | 47.96 | 26.34 / 50.02 | −4.25 |

DS26-0136's prefix winner beat the closest retained held competitor by **84.93 Hz/s** and the cyclic-identity placebo's error was **1,128 Hz/s**. Its early competitor was within **0.25 Hz/s**, far inside the **25 Hz/s** margin. The displaced square returned nearly the same held error with different causal identities. At the forced point, the provisional weakest-axis singular value was **2.14 Hz/s/km**, compared with **2.00** at the centre. Removing RF-proportional clock slope reduced the forced value to **0.97 Hz/s/km**, equivalent to a conditional scale of about **63 km** at the measured residual. The held geographic lead also fell short of the **15 Hz/s** requirement.

DS26-0124's best alternative was **24.43 Hz/s** better on held windows than the training-selected identity. Its forced weak singular value was **0.078 Hz/s/km**, compared with **1.18** at the centre using that point's conditional assignment. One held window leaves a single spatial row after the RF-proportional projection. The omitted square improved the held RF fit while increasing geographic error from **24.70 to 55.18 km**. Zero identities passed the frozen training and held gates in the full roster. [Per-group identity evidence](identities.csv) · [Figure and score seal](score-lock.json)

All 18 workers completed with median **1.79 s CPU**, **2.21 s worker wall time** and **4.68 s end to end** including native handoff. Maximum RSS was **188.2 MiB**. Four component tests cover staggered clock and calibration cancellation, same-emitter copies, a planted distinct triplet and prefix invariance when held observations are absent. [Source seal](source-lock.json)

## Reproduce

```bash
nice -n 10 taskset -c 12-15 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.differenced_orbits_trial \
  /srv/bulk/leo-dev/differenced-orbits-replay
.venv/bin/python -B -m tools.pipeline_eval.qualification.differenced_orbits_results
.venv/bin/python -B -m tools.pipeline_eval benchmark --study \
  reports/2026_11_19_receiver_screening/pilot-search-and-region/differenced-orbits --pack
```
