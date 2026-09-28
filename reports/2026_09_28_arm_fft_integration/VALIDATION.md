# Validation status

The final host integration unit and sanitizer suites pass randomized complex
partial and full 20 ms windows at every supported rate, full zero windows,
overlap-boundary counts, direct retained-candidate identity and score parity,
forced fallback, and a high-dynamic-range block/local-energy fallback case.
The largest unrepaired-grid absolute difference in these deterministic tests
was `9.93410746e-8`. Higher-rate random cases repaired 18--24 epochs.

The frozen host cohort contains 704 dwells and 15,488 windows. It recovered
19,581/19,581 baseline positives with no fallback windows. The experimental
path repaired 272,122 epochs, at most 37 in one window. One original-oracle
`ordered_field` audit fired in the known low-margin ordering case. Independent
paired comparison against the conditioned-CZT host704 result found exact
equality for all 123,904 candidate objects, proving that case is inherited and
not an FFT divergence. See `host704-v1/summary.json`, `HOST_AUDIT.md`, and
`paired-audit.json`.

Independent boundary fixtures passed injected peaks at epochs zero and N-1
for all higher rates, and on both sides of the 5 MS/s overlap step. See
`FFT_EDGE_TEST.md`; this private-translation-unit test remains separate from
the qualified probe and cohort executables.

Final reproducible build locations are:

- host: `/var/tmp/leo-host-fft-coarse-integration-v6`;
- host sanitizer: `/var/tmp/leo-host-fft-coarse-integration-asan-v3`; the
  subsequent changes add the post-grid nonfinite fallback and restore the
  original direct call site at 2.5 MS/s. The FFT arithmetic, normalization,
  repair loop, allocation fallback, and dynamic-range fallback exercised by
  the sanitizer are unchanged;
- ARM candidate with the direct 2.5 MS/s call site restored:
  `/var/tmp/leo-arm-fft-coarse-integration-v5`.

ARM V4 passed the same integration unit. Its 16 saved-IQ probe windows (four
per rate, 128 candidates total) retained candidate-object identity and
matching retained identities against the preceding conditioned-CZT ARM build;
unselected FFT proposal cells are allowed to differ. They measured full-search speedups of 1.1671x,
1.4249x, and 1.6382x at 5, 7.5, and 10 MS/s. Those are small probe results,
not dwell-cohort timings. At 2.5 MS/s the common-wrapper build regressed from
the matched one-repeat CZT mean of 1569.25 to 1596.08 ms (0.9832x) despite
taking the direct branch. V5 restored the direct `coarse` call site; its
matched four-probe, three-repeat mean was still 1589.51 ms with 928.01 ms in
coarse, or 0.9813x the baseline. Therefore do not deploy this combined binary for
2.5 MS/s; use the independently qualified screen-rotation V1 there. No higher-rate
gain should be inferred from the standalone bank measurements alone.

The separate screen-rotation V1 experiment is the selected 2.5-MS/s variant:
1542.867175 ms across its probes and 33912.983283 ms per full dual-RX dwell.
It is independent of this FFT build; these results must not be combined into a
single measured binary or speedup claim.
