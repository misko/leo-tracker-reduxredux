# Carrier CFO versus positive-arrival phase derivative: local coupling, no universal constraint

The predeclared all-source raw-CFO comparison is negative/ambiguous: odd-point RMS is 3.7553 ppm after TRAIN constant centering, versus 3.8587 for fixed +unit and 3.8530 for fixed −unit phase-rate scaling. A pooled TRAIN slope β=0.3094 gives 3.7660 ppm. Neither sign or pooled slope provides reproducible global improvement under the32 conditional permutations. No clock constraint is justified; the audit stops without tuning or localization fitting.

There is limited positive local evidence: many receiver/channel segments show approximately +unit fractional coupling at held points, while other segments reverse sign or have poor scale/alias consistency. Every source/lane and every tested or rejected group is retained. This is not evidence that either reported field is an independently calibrated transmitter clock or known propagation delay.

All693 frozen observations across15 windows were accounted. The exact oldautomatic450Hz/45s/24point builder produced 179 carrier tracklets; conservative phase branch checks left 179 subsegments. There are49 eligible groups/442 observations,234 even phase/TRAIN-centering points and208 odd comparison points;251 observations are in groups shorter than5. Twenty-one quadratic groups contain271 observations/129 odd points. The remaining28 eligible groups use a linear fallback whose centered phase derivative is zero and hence cannot estimate a phase-rate scale.

## Fixed procedure and time/units

The693 observations are the previously selected original winners. No new peak, satellite, orbit, position or station value enters this audit. Group construction is separately per source, using rawwinningCFO, RX/channel and native metadata; window IDs are descriptive output only. Thus the cohort and tracklets are CFO selected, and the alternating test is conditional on that selection, not independent validation. Carrier CFO and phase also come from the same candidate acquisition.

Positive phase is the sealed counter/anchor formula modulo the physical Fs/750 period,3333⅓samples at Fs=2.5MHz. Split at nonpositive first-frame time, adjacent gap>5s, or principal phase increment>quarter period. Alternating TRAIN anchors must also pass the quarter-period guard. This defines a conservative numerical minimal branch, not a verified transmitted frame cycle; unknown cycle slips and alternative anchors remain possible.

Use only even-index phase anchors. Fit degree2 when at least5 even anchors exist; otherwise degree1 with at least3 anchors (totalN≥5). Center polynomial time at the mean TRAIN **first-frame** epoch. Evaluate its derivative at each CFO **support-center** time,8.816–9.483ms later. Set x=(dphase/dt)/Fs and y=CFO/actualRF, subtracting their respective even/TRAIN means per segment. Fixed comparisons are y≈+x and y≈−x, equivalently CFO variation≈±RF/Fs times phase-rate variation. No arbitrary coefficient is fitted to claim this physical equality.

A descriptive β is fitted on even rows only and applied to odd rows; the phase fit never receives CFO. The32 fixed-seed permutations reorder odd centered CFO within each frozen segment. They are descriptive conditional controls, not tests of an unconditional grouping process. Both signs are reported without selecting a sign by results.

## All tested source/receiver/channel strata

| Source / receiver / channel | Groups | Odd N | TRAIN β | Centered baseline ppm | +unit ppm | −unit ppm |
|---|---:|---:|---:|---:|---:|---:|
| S01 / RX1 / CH2 |5|22|0.9714|0.7320|0.2954|1.3888|
| S01 / RX1 / CH4 |9|33|1.0009|0.4968|0.1839|0.9431|
| S02 / RX1 / CH1 |5|16|5.7524|2.0867|2.0838|2.1288|
| S02 / RX1 / CH3 |2|6|1.0565|0.2718|0.1004|0.4956|
| S02 / RX2 / CH2 |3|19|0.9829|4.8322|4.6893|5.2522|
| S03 / RX1 / CH4 |5|28|0.9514|0.8098|0.1527|1.6399|
| S03 / RX1 / CH5 |3|9|0.9976|0.3929|0.2687|0.6311|
| S04 / RX1 / CH3 |5|23|-0.5898|1.0816|2.8276|0.7680|
| S04 / RX2 / CH3 |3|16|0.4905|5.9631|6.0258|6.0069|
| S04 / RX2 / CH5 |4|18|-0.5086|9.9409|10.1075|9.8109|
| S05 / RX1 / CH2 |1|3|undefined|0.4510|0.4510|0.4510|
| S05 / RX1 / CH3 |1|7|1.0366|0.7216|0.0330|1.4158|
| S05 / RX1 / CH4 |3|8|undefined|0.3491|0.3491|0.3491|

## Why a good free slope does not establish another clock observable

For quadratic phase p(t), p′(t) is linear in time. After per-segment constant centering, a free β*p′(t) is exactly an ordinary per-segment CFO linear time trend whenever phase curvature is nonzero. The21 quadratic groups verify this identity: maximum held prediction discrepancy is 1.7e-14 ppm. Their freely scaled held RMS 3.9549 ppm is identically the time-only baseline. Thus improved free-slope fit alone adds no independent measurement constraint. Reproducible fixed scale/sign across groups would be stronger evidence; it is not universal here.

A further ambiguity is explicit:6 eligible groups (57 observations/27 odd points) have rawCFO steps greater than half the CFO alias interval. The carrier linker uses circular CFO, while the predeclared comparison retains raw winning CFO. These groups can dominate aggregate RMS. The primary numbers were not recomputed after choosing an unwrap or removing them. Even the non-alias S04 RX1 CH3 segment has negative β≈−0.590. Therefore the raw global result is both negative and branch limited, and the local +unit examples cannot justify a universal physical relation.

The frame inventory also retains alternative passed phase estimates:551/693 probes have multiple exact numerical fractional phases. Their spread mixes near-identical estimates and widely separated possible anchors. This audit keeps the original winner throughout; it does not resolve which alternative is a physical emitter epoch or estimate phase covariance.

## Prior evidence and external context

The [sealed phase audit](../../2026_10_17_dsx01_iteration6/frame_phase_audit/README.md) established positive arrival-phase semantics and replayed selected phase-versus-frozen-range shapes. It did not establish this all693 carrier/phase-rate relationship. No old/tmp script was imported or executed, and no previous range-sign result is counted as a new result.

Qin et al. distinguish observed timing behavior from a proposed clock architecture. They report that frame and carrier fractional rates can differ, including in sign, and that signals from different beams of one satellite can have different frame phases/rates. This is relevant context against imposing a universal equality, not evidence of the same cause in DSX. See sectionsIVB,IX,X of the [author PDF, Timing Properties of the Starlink Ku-Band Downlink](https://radionavlab.ae.utexas.edu/wp-content/uploads/qin_starlink_timing_properties.pdf).

![All quadratic groups and fixed-sign held errors](phase-cfo-groups.png)

Five component tests pass: modulo seam/guard/gaps, first-frame-to-support derivative transport, exclusion of odd phases/CFO from the fitted phase relation, free-quadratic-slope/time-trend equivalence, and linear fallback. Main calculation elapsed0.223s, far below120s; report rendering is separate. There are zero orbit/localization fit calls and no newRF or reference read. protocol-v2.json binds final code/inputs before target CFO loading; protocol.json is preserved as an earlier preflight that stopped on a manifest-schema mismatch before CFO loading and produced no scientific result. groups.csv/results.json preserve all179 groups and stratum metrics; points.json preserves qualified comparisons.
