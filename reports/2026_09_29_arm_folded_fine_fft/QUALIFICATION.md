# Half-length fine FFT: recovery check

The half-length folded transform is not selected for the preferred detector.
It retains all weighted input samples but samples the spectrum at 1,000 Hz
instead of 500 Hz. This is an algorithmic approximation, not simply a compiler
or storage change.

Actual host evaluation on 32 mixed-rate DS7 dwells ran 704 receiver-specific
windows and 5,632 candidate entries. Against the sealed standard analysis,
it recovered **805/843 individual positive hits**, with 1,044 unmatched
positive entries. The preferred two-frame method recovered 835/843 on this
panel. The extra 30 misses do not justify promotion or a larger ARM timing run.

Evidence: `../2026_09_29_arm_subsecond/host32-folded-fine/standard-audit.json`,
its manifest, rows and frozen build receipt. Host recovery does not establish
ARM runtime or numerical equivalence. No ARM speed claim is made for this
variant. The ongoing subsecond objective remains unmet.
