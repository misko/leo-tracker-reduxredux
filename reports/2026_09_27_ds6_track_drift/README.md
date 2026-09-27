# DS6 per-track linear drift experiment

Training-profiled per-track slopes improve held prediction on all four frozen
development scans but worsen geographic error on three, including the preceding
sub-kilometre case. This model is not promoted as a position-accuracy fix.

| MS/s | Previous calibrated-scale error (km) | Track-drift error (km) | Held log-score gain |
|---|---:|---:|---:|
| 2.5 | 3.779 | 6.744 | 287.56 |
| 5 | 7.291 | 3.572 | 270.86 |
| 7.5 | 0.489 | 4.749 | 357.42 |
| 10 | 6.202 | 7.452 | 129.48 |

The protocol was frozen before fitting: Student-t4 observation errors, inherited
training-calibrated scales, an independent slope per track under a zero-mean
10 Hz/s Gaussian prior, and training-profiled offsets. Each catalogue candidate
gets its own training-only nuisance fit. The constant offset prior remains
1 MHz. Whole-visit random partitions, inputs, causal catalogue, and approximate
candidate shortlists are unchanged. Four starts optimize position and shared
scan timing on the training score only. The fitting script does not load the
operator coordinate; a separate summarizer scores the frozen output.

All sixteen starts converge, and all four winners are inside the local bounds.
Repeating the inner fit with 60 instead of 30 IRLS iterations changes training
score by at most 0.000035 and held score by at most 0.050. All three tests pass:
synthetic slope/offset recovery and held isolation, outlier and zero-span
numerics, and frozen real-data provenance/selection/numerical audit.

The median absolute fitted slope ranges from 7.4 to 13.1 Hz/s. These are effective
model residual terms, not measurements of hardware drift. A per-track slope can
absorb geometric Doppler as well as frequency-system effects. Better prediction
therefore does not establish better geometry, as the geographic results show.
The scores profile slopes rather than integrate them, and the inherited
shortlists may omit candidates favoured by the broader model. This is not a
global catalogue search, full uncertainty calculation, or DS6-wide validation.

The full 43-scan numerical export runs separately in `2026_09_27_ds6_cfo_dataset`.
The next validation should establish a fixed-model baseline across the complete
dataset rather than choose a model from these four geographic outcomes. No RF
was collected and no production code was changed.
