# FP32 coarse-search divergence audit

The sole observed strict ordered-parity divergence in the completed all-sealed
screen run is DS7 ordinal 306 (`scan-fw-43e84176a367910b`, visit 693), 7.5
MS/s lower edge, receiver 0, probe 3. It is not a margin-gate recovery miss:
the affected candidate is negative in both paths, and all 37 positive
hypotheses in that dwell remain recovered.

I ran the same saved CI16 dwell through the separate full-FP64 baseline cohort
binary. Its receiver-0/probe-3 candidate at epoch 5499 has fine CFO 190000 Hz,
conditioned/acquired CFO 191127.3696556345 Hz, and margin
0.00042350304152159735. Those values match the sealed original baseline. The
screen run instead retained the same epoch but used fine CFO 141500 Hz and
conditioned CFO 139551.30483844355 Hz, producing margin
0.0016079992892837763 and moving that candidate from rank 1 to rank 4.

The seven other candidates agree when matched by epoch, but ranks 1 through 4
shift, so four ordered positions mismatch. A coarse32-only reproduction isolates
the cause: it produces the candidate-binary values exactly at epoch 5499
(coarse bin 7, fine CFO 141500 Hz, conditioned CFO 139551.30483844355 Hz).
The FP64 baseline uses coarse bin 8 and fine CFO 190000 Hz. The fine-CFO branch
therefore changes at coarse-basin selection before conditioned scoring. The
evidence attributes this divergence to FP32 coarse accumulation, not the
conditioned screen or an intrinsic FP64 native-port difference.
