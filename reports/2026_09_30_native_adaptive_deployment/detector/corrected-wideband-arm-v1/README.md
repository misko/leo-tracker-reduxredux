# Corrected wideband detector: bounded ARM measurement

The isolated 22-slot server-reference research detector processes saved DS9
visit 301 on physical PLUTO+ `192.168.1.15` in **55.300 seconds of detector-call
wall time for a 120 ms dwell**, a ratio of **460.83**. Whole-process time is
55.68155 seconds, CPU time 55.66786 seconds, peak RSS 40,244 KiB, exit 0.
This is one CPU-only measurement, with no concurrent root-owned device job or
new RF collection. It does not qualify real-time or capture-concurrent operation.

The corrected geometry is receiver center -312,500 Hz for both receivers,
residual bounds -800,000 through +800,000 Hz, 7.5 MS/s and 120 ms dwell/stride.
These values come from the previously reviewed visit-301 authority; only the
schedule's filesystem paths change for the ARM device. The mode is
`--deployed-server-interval-fractional`. Its scientific probe semantics remain
those of the frozen wrapper; the dwell duration is the available processing
budget, not a claim that every sample in the dwell contributes to a fit.

Both receivers match the corrected host wrapper: 16 retained candidates have
equal rank, integer epoch, fractional status and nullability. All ten compared
numeric fields satisfy the frozen 1e-6 Hz / 1e-10 scalar tolerances. All 12
complete-candidate gate decisions agree, including seven passing candidates;
four fractional results are unavailable. Maximum fractional offset difference
is 3.56e-15 samples, maximum score/margin difference 2.23e-16, and compared CFOs
are equal. This is ARM/host wrapper parity on one visit, not full-corpus ARM
or end-to-end location qualification.

Profiled search consumes 55.2505 CPU seconds, versus 0.0351 seconds preparing
samples. This identifies search as the dominant cost. No ordinary production
detector, application, firmware or golden fixture was changed by this test.

The ARM executable SHA-256 is
`661dde13cfe9cd4518e421afa2b5820a02ab83266b6bc07d64d1c0ceaadfd877`.
`artifacts/build-receipt.json` binds the frozen wideband source, compiler,
flags, build commands and link inputs. The device's dynamically loaded FFTW
library `/usr/lib/libfftw3.so.3.6.10` has SHA-256
`1331a476804e5812490f15c18f4b087859552716fb5933413606482642d61a19`;
it differs from the toolchain's link-time library, whose hash is recorded in
the build receipt. The observed numerical comparison covers this installed
runtime library. No system library was replaced.

`installed-sha256.txt` verifies the installed executable, templates, schedule
and raw input. `comparison.json` binds both outputs and the reviewed comparator.
The raw input is retained at its existing fixture location rather than copied
into this report. The device-only test directory is
`/mnt/glrtbench/native-adaptive/tests/corrected-wideband-v1`.

The measured command was:

```sh
/mnt/glrtbench/native-adaptive/current/measure-run 120 \
  /mnt/glrtbench/native-adaptive/tests/corrected-wideband-v1/leo-native-adaptive-replay \
  --manifest /mnt/glrtbench/native-adaptive/tests/corrected-wideband-v1/visit-0301.arm.tsv \
  --deployed-server-interval-fractional
```

Reproduce the scientific comparison from the repository root using:

```sh
/var/tmp/leo-arm-realtime-publication/.venv/bin/python \
  reports/2026_09_30_native_adaptive_deployment/detector/corrected-wideband-arm-v1/compare_to_host.py
```
