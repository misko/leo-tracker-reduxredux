# TG11 screen-coordinate audit

This is a read-only audit of the frozen stage-0 implementation and receipts. No
IQ was evaluated and no frozen source, threshold, or result was changed.

## Finding

The repeated-pilot `blind_screen_disagreement` routes have a concrete and
sufficient explanation: TG11 compares the 512-bin rank proposal directly to
the refined acquisition epoch, but the frozen evidence shows that those two
numbers are not interchangeable for the repeated 2.5 MS/s control.

For `lag3-r2500000-pilot-cfo0-int`, the earlier frozen adversarial-transfer
receipt records rank `projected_epoch_samples = 1771` for every 20 ms slice and
both receivers, while the reference full acquisition reports 316.598 samples
for RX0 and 317.103 samples for RX1
(`new_data/fft32_adversarial_transfer/results.json`, lines 647--725 and
799--878). The frame period is 3333.333 samples, so the circular discrepancies
are about 1454.4 and 1453.9 samples, or 581.8 and 581.6 microseconds. The TG11
innovation gate is 4 microseconds, or 10 samples at 2.5 MS/s.

This prior receipt is applicable to the TG11 screen statistic: both artifacts
pin `window_rank.c` SHA-256
`cb7d5c137a28cc1cbbc52c579eade8cee569eac201fe668f86407fde69e24e07`,
`blind_strided_v4.c` SHA-256
`df1b19988122acafc1934888d385878d8224438fc86996db202126dba69cdc00`,
and native profile SHA-256
`3c96186ad0e22b6e948f90ad9fd33a54508c94ae6e376b367064d36b804fc1a1`.
The hashes appear in `tg11/source_lock_stage0.json` and
`new_data/fft32_adversarial_transfer/source_lock.json`.

The stage-0 sequence receipt is consistent with this mismatch. On the second
copy of the same array in both `pilot-dropout` and `changed-pilot`, RX0 blind
acquisition returns local epochs 317.428 and 317.412, and RX1 returns 316.599
and 316.630, all with margins from 0.923 to 0.944. Nevertheless, both receivers
route `blind_screen_disagreement` with zero guided attempts
(`control_results.json`, lines 4709--4865 and 5193--5349). The 300,000-sample
visit advance is exactly 90 frame periods, so the state fitted from the first
copy predicts the same local phase on the second copy. A large margin does not
help because the screen gate runs before guided GLRT scoring.

## Source path

The incompatibility follows from these frozen paths:

1. `tg11_native.c` lines 51--63 folds each probe with the lag-4 rank kernel and
   copies `timing.epoch` into the projection row. Lines 75--82 select one row
   and publish that integer without a coordinate transform or calibration.
2. `native_engine.py` lines 226--249 passes that integer through verbatim as
   `ScreenWindow.projected_epoch_sample`.
3. Blind acquisition follows a different path. `tg11_native.c` lines 118--140
   calls the complete unseeded presence acquisition, and `native_engine.py`
   lines 260--276 defines its local epoch as the fitted integer epoch plus the
   fractional offset modulo the frame period.
4. `decision.py` lines 289--332 predicts the latter fitted acquisition
   coordinate from the saved source-counter anchor. Lines 557--585 then compare
   the rank number directly with that prediction and fall back to blind unless
   at least two non-overlapping windows are within 4 microseconds.
5. The rank kernel itself builds and correlates a projected lag-4 differential
   sequence (`window_rank.c` lines 209--230, 250--306, and 310--333). Its public
   header calls the returned epoch "approximate" and says it must not replace
   fractional GLRT confirmation (`window_rank.h` lines 26--30). It does not
   state that the integer is calibrated to the refined acquisition epoch.

The 512-bin projection has a bin width of about 6.51 samples at 2.5 MS/s, so
ordinary nearest-bin quantization cannot explain an approximately 1454-sample
error. Reusing the identical array makes the rank proposal stable, but it also
makes a stable rank-versus-acquisition disagreement repeat. That is why a
stable state estimate can still take the disagreement route.

## What is and is not established

The frozen evidence establishes that direct equality of the two epoch values
is false for the exact control used by both repeated-pilot sequences. It does
not establish a universal correction. Other frozen adversarial controls show
different offsets: at 5 MS/s the zero-CFO control happens to agree within about
1.5 samples, while several CFO/channel variants have errors of hundreds or
thousands of samples. A single fixed subtraction is therefore unsupported.

The source also does not establish that the discrepancy is specifically a
cyclic-prefix, OFDM-symbol, or frame-origin convention. The stronger supported
description is that a coarse lag-differential correlation index is being
treated as though it were a calibrated refined-GLRT epoch. Aliased correlation
peaks, projection/resampling, and signal-dependent ambiguity remain possible
mechanisms; identifying one would require recording both projection rows and
the state prediction for each window under a separately frozen diagnostic.

No claim about native guided sensitivity follows from stage 0. All 52 positive
control decisions were found by blind acquisition, and none reached a guided
measurement. A later qualification should first require rank-to-refined timing
association across rate, edge, CFO, channel, and ambiguity strata before using
the rank proposal as a hard gate on cached predictions.
