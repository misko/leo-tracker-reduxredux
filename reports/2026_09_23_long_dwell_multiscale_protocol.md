# Frozen protocol: 105915 independent-chunk phase recovery

Use stream 0 of `cap-20260825T105915-2770b84587cc`, corrected channel-4 upper
pilot, and the two historical source epochs and four affine receiver carrier
models. Fixed centers are 24.0, 25.5, 27.0, 28.5, and 30.0 s. Durations are
600, 300, 150, 120, 60, and 20 ms. Each center's largest read is 600 ms; reads
do not overlap. Select the same frame ordinals for both sources with RNG seed
20260923 into train and held. Guard each chunk boundary by 117 samples.

For each chunk and source, search a common RX0/RX1 integer timing shift on train
frames only. Demodulate each receiver with its frozen affine carrier in absolute
capture coordinates. Mode `frozen_timing` uses the historical 20 ms timing
shift at the same center. Mode `local_timing` uses the train-only search. Both
fit one receiver-product residual frequency on training frames. Held frames
measure phase at the common center using that frozen frequency; the training
intercept is retained separately. Restore both historical carrier phases at
the declared physical center exactly once, form source phases independently,
then form ordinary-2π source double difference. No per-chunk phase alignment is
allowed. Rolled-17 pilot and wrong
timing are controls. Retain every failure.

Compare each result to the previously retained 20 ms phase curve at the same
center. This is a reproduction/attribution experiment on previously inspected
IQ, not fresh validation. It tests independent chunk recovery, not coherent
integration over the seven-second span.
