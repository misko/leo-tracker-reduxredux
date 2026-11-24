# Per-visit block-floating IQ on one signed physical member

Use the already resident first signed DS30-0016 member, 64 issued visits
including the original exclusions, with its authenticated manifest,
index, compressed payload and decoded digest. Decode it once. Run the
unchanged 20/8 mixed native receiver on the original, the 8-bit
reconstruction, then the conservative 10-bit reconstruction. Use only
the original capture metadata for eligibility, channel, sample counter
and aperture scheduling. Keep the same two receiver lanes, pilot,
native hashes, rank selection and chronological continuation. Archive the
raw native factors before the strongest-factor choice and the actual
selected rows, including empties. No solve, RF, extra recording, or
original backing-storage reads.

Each encoded visit has one exponent adjusted to the smallest power of
two for its measured signed range across both I and Q and both receivers.
Round to nearest, ties away from zero, with signed saturation. Eight-bit
data holds one signed byte per word. Ten-bit data stores four consecutive
signed words in five bytes. Decode into contiguous signed CI16 for the
same receiver. Quantize and reconstruct all 64 visits without replacing
any original bytes. Record the exact packed byte count inclusive of
exponents, measured per-stage CPU and wall, range, saturation and
original/encoded/reconstructed digests. Hashing, audit output and
waveform hydration have separate boundaries from the codec kernel.
Separate future ingest from any conversion of an already compressed
original. No claims of lossless archive custody.

Require the original arm to reproduce the earlier independently signed
20/8 packet prefix before qualifying the comparison. Compare every
original opportunity by issued visit, lane and rank. A retained branch
must be within two samples modulo the 13,333-sample pilot period and
250 Hz in signed CFO. Count promotions, missing ranks, empty lanes,
selected rank switches, continuation votes and retained short lanes
before looking at any position. Even stable branch totals must preserve
matched lane membership to support further work. The 10-bit control is
predeclared and neither width will be tuned to the prefix. Stop after
these two representations on this member. Serialize under the shared
Gauss lock, CPU 2, nice 15, I/O priority 7, one numerical thread.
