# Rejected CI16 conditioned-energy prefix reuse

The prototype reuses normalized CI16 energy prefixes to obtain each contiguous
conditioned frame's received energy. CI16 per-sample squared energy is an
integer at most 2^31; through 2^22 source samples the total is at most 2^53.
The original sums, normalized prefix differences and power-of-two rescaling
therefore represent the same integer exactly in binary64. The owner attests
the entire source length before borrowing a prefix slice, and clears the
attestation after the search returns. Generic inputs retain direct summation.

The saved standalone test exercises every signed-16 value, full-scale extrema,
empty windows, offset slices and prefixes near the proof limit. Host, physical
ARM and sanitizer checks pass. The detector's 18 existing host tests also pass.
Reproduce the numerical test with `cc -std=c11 -O3 -fno-fast-math -Isource
test_ci16_energy_prefix.c -o /var/tmp/test-ci16-energy` from this directory.

The physical ARM experiment uses 32 evenly spaced existing DS9 dwells in
control/new/new/control order, with matched ordinary builds and 60-second
per-process limits. All scientific fields and execution diagnostics match the
saved reference. Mean call CPU is 103.248735 ms for control and 103.415417 ms
for the prototype: no useful whole-detector gain. Conditioned scoring alone
gets slightly faster, but that does not establish a pipeline saving.

`../ci16-window-energy-v2/` tests an explicitly separated fast loop. Both
variants were rejected and all production changes were reverted. Source
snapshots, build commands, hashes, numerical test and measurement receipts
remain here; no frozen fixture or qualified detector binary was replaced.
