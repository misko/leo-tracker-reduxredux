# Can the first scout already see the second carrier?

The frozen receiver's existing nonlinear first scout contained **29 of 36** exact residual targets among its top three coarse seeds. Refining those raw seeds and running both original gates proved that the raw samples also supported those carriers. The other seven targets had no matching phase among the 12 retained timing maxima. Their best raw timing-grid ranks ranged from **55 to 896**, despite released residual margins of **0.138–0.287**. Keeping more of the existing 24 carrier seeds cannot recover a target whose timing phase was omitted. [Ranks for all examined lanes](receiver-shortlist-results.json)

The fixed scope was the same 68 physical lanes used in the linear projection experiment. An instrumentation-only build reproduced the frozen receiver's exported factors on every lane. The audit used each frozen residual factor's measured epoch and signed CFO to inspect the original raw scout. Separately, an executable shortcut chose a second candidate using only the current lane's data. Neither used position or orbit information. [Earlier linear scout](receiver-projection.md)

| Stage | Ordinary slice | Weak-carrier slice | Total |
| --- | ---: | ---: | ---: |
| Valid lanes | 32 | 36 | 68 |
| Confirmed first passes eligible for a residual scout | 19 | 36 | 55 |
| Released verified residual targets | 14 | 22 | 36 |
| Target phase covered by a retained raw timing maximum | 11 | 18 | 29 |
| Target represented in the unpruned 24-seed raw carrier list | 11 | 18 | 29 |
| Target present after native refinement and both original gates | 11 | 18 | 29 |

The 29 verified raw seed ranks were 6 at rank one, 22 at rank two, and 1 at rank three. On the eligible timing rows, the best bin within native coarse capture range ranked first for all 29. The timing audit used up to seven wrapped samples and 4.55 kHz before refinement, corresponding to the native refinement aperture plus the release's matching tolerance. A refined seed had to be within two wrapped samples and 1 kHz signed CFO. The independent frame-group confirmation and the exact/rolled fractional margin still had to pass on the untouched samples.

## A running shortcut with independent residual confirmation

The executable keeps the exact first winner and inspects the existing four refined raw candidates. It requires exactly one distinct alternate to pass raw confirmation. It applies the original per-block fit and signed integer cancellation, then tests the alternate's original coarse timing and CFO seed against the actual residual. The local result must remain within two samples and 250 Hz of that raw alternate and pass the original residual frame gate. Both outputs pass the unchanged fractional verifier on the original I/Q. Missing, ambiguous, or failed local candidates fall back to the complete residual scout. If a locally confirmed residual then fails the original fractional verification, the call retries the complete detector.

The shortcut tried local refinement on **25 of 55** residual scans. It used the local confirmation on **22** and the full residual scout on **33**. No fractional rejection required repeating the whole detector. Whole native CPU across both slices fell from **0.343 to 0.318 s** and from **0.348 to 0.324 s** in the two repeats. Two of the 68 lanes had changed factor tuples. The weak-carrier slice retained its exact tuples on all 36 lanes.

DS26-0020 visit 3923 RX0 was the decisive counterexample. The shortcut kept the first measurement at −211.944 kHz. Its locally confirmed alternate at −207.245 kHz had fractional margin 0.196. The full residual search instead found −60.019 kHz at a different epoch with margin 0.183. The full search's target ranked 245th in the raw timing grid. A second changed lane, DS26-0036 visit 301 RX0, retained the same residual within the matching tolerance and shifted its signed CFO by 14.65 Hz. This rejects the shortcut for the exact publication candidate. An independently confirmed alternate, even one with a higher fractional margin, cannot certify the full residual scout's choice.

The raw shortlist evidence gives at most 29 observed opportunities to avoid the full residual scout by this route across the 55 confirmed first passes. At the frozen mean timing-pass cost of about 1.8 ms, removing those 29 scouts without charge would save about 52 ms, roughly 15% of the 0.35 s native CPU measured across these enriched slices. Cancellation and the final verifier still run. That arithmetic assumes mean scout cost and a perfect routing decision. The measured savings with actual routing were lower, and the higher-quality result still requires the full residual decision. [Frozen timing-pass profile](receiver.md)

## Reproduce

The comparator is the frozen `107909cc` receiver. Selection uses the first 16 sorted entries from the existing prospective archive and the 18 previously nominated weak/challenge visits. The timed shortcut rotates arm order across lanes and repeats. Benchmark clocks include all native gates and fallbacks and end before archive decoding and localization.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_venv=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock "$algo08_venv" -m "$algo08_native.receiver_build" "$algo08_work/receiver-shortlist-audit.so" --shortlist-audit
algo08_lock "$algo08_venv" -m "$algo08_native.receiver_shortlist" \
  "$algo08_work/receiver-final-candidate.so" "$algo08_work/receiver-shortlist-audit.so" \
  /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  --assets /opt/leo-algo08/current/assets
algo08_lock "$algo08_venv" -m pytest -q tests/pipeline_eval/test_experimental_receiver_shortlist.py
```

Two component tests passed. They exercise absent and pruned rank accounting, a planted signed raw carrier with independent confirmation, and exact residual fallback in the sole-carrier case.
