# Batched fine FFT qualification

The two-frame FFTW batch preserves every candidate object on the completed
704-dwell mixed-rate DS7 evaluation: 15,488 windows, 123,904 candidate entries,
and **19,249/19,581** original standard GLRT hits recovered. Unmatched positives
remain 21,555. The physical ARM component suites also pass, including every-bin
batch-versus-separate FFT comparison at all four supported rates.

On four saved 2.5 MS/s dual-RX dwells, CPU0 search measured **1.296940 seconds
per dwell**, versus the separate-transform reference's repeated mean of
1.280431 seconds. Fine FFT time was 306.418 ms. All ARM candidate objects were
identical to the reference. This single timing run shows no speed improvement;
batching is not selected for the preferred method. Proposal generation,
initial setup, file loading and simultaneous capture are excluded.

Evidence is in `arm-units.json` and sibling
`../2026_09_29_arm_subsecond/{host704,arm4}-batched-fine-radius2` manifests,
receipts, summaries and host standard audit. Packing two general complex FFTs
into one does not remove a transform; this experiment changes execution
scheduling, not the number of mathematical transforms or their precision.
