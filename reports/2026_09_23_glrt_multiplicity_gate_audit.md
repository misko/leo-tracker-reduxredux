# Multiplicity gate audit for the adaptive GLRT plot

This audit reconstructs the candidate pairing gates from the published analysis
metadata for `scan-hop-28d7592ea614f624`. It reads no IQ and makes no change to
the production detector. The machine-readable receipt is
[`gate-audit.json`](figures/2026_09_23_scan_glrt_multiplicity/gate-audit.json),
created by
[`audit_adaptive_glrt_multiplicity.py`](../tools/research/audit_adaptive_glrt_multiplicity.py).

The published product contains one 20 ms GLRT probe at start zero for each
120 ms dwell. It is therefore a candidate inventory at that fixed probe, not
an exhaustive new search through each 120 ms capture.

| Metadata-only stage | Visits / records |
|---|---:|
| Published dwells | 2,360 |
| RX0 with two or more passed candidates | 199 |
| RX1 with two or more passed candidates | 827 |
| Both receivers with two or more passed candidates | 136 |
| Both receivers with two or more alias-aware 5 kHz frequency groups | 9 |
| Two or more one-to-one timing/receiver-offset matches, before source deduplication | 112 |
| Two or more final distinct matches | 5 |
| Pre-deduplication selected pair records | 375 |
| Final distinct pair records | 263 |
| Rejected pair records | 112 |

The first large reduction is already visible without cross-receiver matching:
of 136 visits with at least two passed records in both receivers, only 9 retain
two 5 kHz-separated frequency groups in *each* receiver after folding the
227.27 kHz symbol-frequency alias. Thus many plotted GLRT peaks are repeated
candidate hypotheses on one receiver, not evidence that it independently
resolved several emitters.

The later 112-to-5 reduction is almost entirely an alias/duplicate cleanup.
Every one of the 112 rejected selected pairs collides within 5 kHz in **both**
receivers with an earlier retained pair. Their minimum alias-aware separation
is below 1 Hz for 91, 1–100 Hz for 9, and 100–5,000 Hz for 12. All 112 also
have RX0 source-epoch separation at most one sample from their retained
conflict, and their paired RX timing residual is at most one sample. Their
candidate ranks differ, so rank multiplicity is not independent source
multiplicity; the associated timing and CFO hypotheses are nearly coincident.

The 12 pairs between 100 Hz and 5 kHz should still be described carefully.
They are close, same-epoch hypotheses under this metadata product and are
conservatively deduplicated. That is strong evidence against treating them as
separate source observations, but it does not prove that two physical signals
were absent. A real component that only one receiver can separate would fail
the deliberately symmetric distinctness rule.

The phase-blind pairing route is: retain only candidates that passed the
persisted fractional-margin gate; require RX epoch agreement modulo the
1/750 s frame period within nine samples; find one-to-one edges sharing an
alias-aware RX1-minus-RX0 tracking-CFO offset within 10 kHz; then reject a
second edge within 5 kHz modulo the 1/4.4 us symbol alias in either receiver.
The gates do not inspect measured phase, catalogue identity, or a desired phase
outcome. They do condition later phase replay on the archived GLRT timing and
CFO hypotheses from the same 20 ms probe, so any held-frame phase result is a
conditional measurement check rather than an independent acquisition test.
