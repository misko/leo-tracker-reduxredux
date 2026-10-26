Completed bounded negative screen; see FINDINGS.md and summary.json. Three
owned causal/counter/ambiguity tests pass. Metadata-only panel and source seal
were generated before predictions or IQ. All 48 paired target windows pass
original historical exported-candidate parity; the numerical stage took 82.18s.
The audit reproduces 96 forecasts and fresh response-redaction/nonoverlap checks.
No complete mode passes both target half margin gates under either constant
or linear forecast: 0/5 eligible cells, 0/96 requested cells. No position admission.

Frozen SHA256 values:

- protocol.json: f7c58b09ab9c02a3458c265969941286e96083aceab9f1fbbe836af0c5b3324b
- panel.json: 3832ff6212d74161a7f703a89ab2c99a0bb963f6c215f64d37b20e29aa4fb067
- predictions.json: 4e10d8bb9bca7338d117d708a46df8a675f40cee60f07af7f64fc40523679159
- results.json: 308b566658924b62b5897a9486208c5c54276ccbfb8adab23c60cc52371e81d2

All 48 target windows have public raw metadata. Only 5/96 receiver cells have
an unambiguous three-visit mode (CH1:1, CH5:1, CH6:3, CH4/7/8:0). There are
8 complete modes, 33 missing-history modes and 6 ambiguous modes; 91 cells
have no complete mode and remain in the denominator. No tuning/reselection.
Availability funnel: latest donor 24/96; at least 2 of 3 visits 23/96; all 3 visits 6/96;
unique compatible history 5/96. CH7/8 have no all 3 passing histories. Per CH/RX
counts and matched-mode CFO/timing rates are in summary.json/cells.csv.

Interface: `panel.json.slots[*]` binds `request_id` and public `raw_authority`
for one paired 20ms target. `cells[*].header` has case, channel, edge,
receiver_id, sample_rate_hz, target_start_counter, target_visit_index.
`cells[*].earlier` has exactly the preceding three same-cell persisted probes.
`target_original` is evaluation-only original fullwindow acquisition exposure.

`predictions.json.rows[*]` repeats the header and contains `forecast.modes`;
each mode has original `seed_rank`, explicit complete/missing/ambiguous status,
the donor counters/ranks/times and CFO/phase values, constant and linear
`epoch_samples`/`CFO_hz`, and fit rates/residuals/heuristic uncertainty widths.
`forecast.primary_mode` selects the first complete unambiguous original rank.
No mode is selected by target response. Hashes and freeze time follow shortly.

The first target may serve as an earlier fullwindow measured donor to the
second target; these paired targets have shared donor samples and must not
be counted as independent experiments. Each target's two half scores have
disjoint support conditional on the earlier-only forecast. Original fullwindow
target acquisition was previously exposed; half agreement is labeled support
consistency and never independent ground truth or external identity validation.
