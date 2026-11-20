# Competing region hypotheses

The challenger withheld all six matched archive runs and all three omitted-region runs in both calibration arms. The joint-pass incumbent returned two matched fixes and withheld all three omitted runs. The challenger failed its independent native-validation gate on every archive case, so disabling the outside comparison alone would recover none of the incumbent fixes. [Archive position errors](position-errors.csv) · [Matched predictions](matched-tile.jsonl.gz) · [Omitted predictions](omitted-tile.jsonl.gz)

Both arms had 8.193 km median forced error on the matched archive. Median conditional RMS on genuinely reserved probes was 8,464 Hz at zero calibration and 8,465 Hz with fitted calibration. The paired fitted-minus-zero medians were +0.001 km in forced error and +1.08 Hz in held carrier RMS. The incumbent's RMS comes from the tails of its own linked tracklets. The challenger reserves different native probes before linking, so the frequency columns describe each receiver's own observations. [Conditional frequency, competition and gate rows](conditional-frequency.csv) · [Paired summary](summary.json)

## Prospective synthetic results

The independent fresh panel locked both receivers and their dependencies before drawing each cohort. The exact and perturbed cohorts each had four containing offers, four omitted offers and one shuffled capture. The perturbed generator changed emitter orbit epoch, oscillator behavior, epoch readout and visit availability. Neither receiver returned a fix on either shuffle. [Prospective protocol and scores](../fresh-transfer/README.md)

| Cohort and receiver | Containing returns, zero / fitted | Returned median error in km, zero / fitted | Omitted false fixes, zero / fitted |
|---|---:|---:|---:|
| Exact, joint-pass incumbent | 4/4 / 4/4 | 1.143 / 0.448 | 0/4 / 0/4 |
| Exact, region challenge | 4/4 / 4/4 | 0.073 / 0.046 | 0/4 / 0/4 |
| Perturbed, joint-pass incumbent | 4/4 / 4/4 | 0.602 / 1.138 | 0/4 / 0/4 |
| Perturbed, region challenge | 1/4 / 1/4 | 1.205 / 1.204 | 1/4 / 1/4 |

Without outside competition, the challenger would have returned all four containing perturbed cases and three zero-calibration or four fitted-calibration omitted cases. The outside test withheld three valid containing offers in each arm. It also withheld the one native-gate-eligible omitted case in the exact cohort. The remaining false return in the perturbed cohort was 75.531 km from truth with zero calibration and 75.495 km with fitted calibration. The offered center was 79.844 km from truth, beyond the approximately 53 km reach of the adjacent square halo. The false inside fits still beat the strongest outside by 24.12 and 7.77 score units and had held carrier RMS of 426 and 425 Hz. These held data discriminate among the tested tiles. A restricted halo can strongly favor an incorrect tile when every tested tile misses the site. [Post-seal gate audit](fresh-gate-audit.csv) · [Fresh per-case scores](../fresh-transfer/scores.json)

## Equal-complexity region test

The original 25 km square and its eight adjacent squares use the same candidate model, five training starts, fit budget and calibration priors. The fitter reuses 33 shared starts and a single causal orbit bank. Each square selects identities and orbit time shifts from the training prefix before profiling position and frequency terms. The two calibration arms use the same selected samples, identities and orbit time shifts within each square.

The final 1.4 s of each 10 s hardware interval is removed before forming tracks. The nine hypotheses predict the same gated held probes on lanes with training support. Carrier and frame predictions are compared to circular clutter, and each occupied 10 s block contributes one mean log-likelihood ratio. The inside fit must beat the strongest outside and exceed 8:1 composite odds against the equal-weight outside mixture. The independently held carrier, frame and coverage checks apply separately. Forced outputs always use the inside fit. [Protocol](PROTOCOL.md) · [Implementation](../../../tools/pipeline_eval/variants/region_challenge.py)

All nine isolated workers finished within 100 s on one CPU each. Matched median wall time was 26.60 s with a 45.52 s maximum. Omitted median wall time was 32.62 s with an 84.44 s maximum. The separate scorer checks the exact offers and native/TLE digests against the joint-pass incumbent. Geographic labels stay outside the prediction workers. [Source lock](source-lock.json) · [Component tests](../../../tests/pipeline_eval/test_region_challenge.py)

```sh
nice -n 15 .venv/bin/python -m tools.pipeline_eval.qualification.region_challenge_trials \
  --scratch /tmp/region-archive --report /tmp/region-report --cpus 6 7
.venv/bin/python -m tools.pipeline_eval.qualification.region_challenge_trials \
  --score --report /tmp/region-report
.venv/bin/python -m tools.pipeline_eval.qualification.region_challenge_trials \
  --fresh-report reports/2026_11_19_receiver_convergence/fresh-transfer \
  --report /tmp/region-report
```
