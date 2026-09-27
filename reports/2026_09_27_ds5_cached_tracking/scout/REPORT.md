# Development scout result

Neither frozen scout is suitable for holdout qualification. At thresholds chosen
to retain all 36 development reference positives, native rank routes 222 of 256
receiver-visits (86.7%) and sparse lag-3 routes 231 of 256 (90.2%). Their
zero-cost scout ceilings are only 1.191x and 1.129x. Including measured receiver
packing and the complete call gives modeled speedups of 0.767x and 0.803x.

The sparse kernel itself costs a median 0.034 ms at 2.5 MS/s and 0.131 ms at
5 MS/s. Full measured calls, including extraction of one receiver into contiguous
CI16, cost 0.594 ms and 1.282 ms. Rank full-call medians are 0.812 ms and
1.604 ms. These server measurements do not predict ARM timing, but the route
fractions alone rule out a 10x result even with a free scout.

The independent prior controls do not rescue either design. Every one of the four
receiver-controls in each rate-by-kind cell (pilot, noise, and tone at 2.5 and
5 MS/s) routes under both development thresholds. Controls were evaluated only
after threshold selection and did not change either threshold.

This is a reference-relative screen audit. A nonroute is only
`measured-screen-negative`; it is not confirmed absence or a noise label. The
5 MS/s threshold is unverified because the development reference has no 5 MS/s
positives. No fresh holdout IQ or outcomes were opened.

The immutable result is `results.json`, SHA256
`e21e363e28dba103c9336fad411b59c71700282647ef9089d9b18b9821795e18`.
`decision.json` records the decision not to promote either variant.
