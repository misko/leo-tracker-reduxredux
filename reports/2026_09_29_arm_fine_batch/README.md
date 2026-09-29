# FP64 fine FFT batching prototype

This report-local prototype starts from the frozen `arm_fine_reuse` host-v4
and ARM-v3 sources. It replaces the sixteen individual fine-stage FFTW calls
for a newly encountered epoch with `fftw_plan_many_dft` batches of four or
sixteen. Epoch population remains lazy. Template energy, per-frame signal
energy, denominators, magnitude extraction, frame accumulation, and final
division retain their original scalar order.

The plan and aligned batch arrays are initialized once per full-search call.
Initialization occurs after coarse acquisition under the existing fine-stage
CPU timer, so planner setup is included in both `fine_fft_cpu_ms` and
`total_cpu_ms`; it is not excluded as untimed setup. `FFTW_ESTIMATE` avoids a
runtime planner search. A short final batch is zero-padded, and only its valid
lanes are retained.

The inherited component test compares the batched scores byte-for-byte with
the original scalar FFTW path for full and partial dwells at all four sample
rates, four frequency ranges per dwell, cache reuse, and cache reset. Both
batch sizes passed with bitwise equality on the host. Batch four also passed
AddressSanitizer and UndefinedBehaviorSanitizer with leak detection. ARM
binaries were cross-compiled with Cortex-A9/NEON flags but were not executed;
the root evaluator owns serialized ARM measurements.

Evaluator inputs are `builds/host-batch4/build.json` and
`builds/host-batch16/build.json`. Their candidate JSON schema and cohort CLI
are unchanged from the frozen source.

The canonical proposal overlay is in `src/`. Reproduce a build into a new,
nonexistent directory without modifying measured artifacts, for example:

```sh
python3 reports/2026_09_29_arm_fine_batch/build.py \
  --target host --batch 4 --output /var/tmp/leo-fine-batch4-rebuild
```

Use `--target arm` for an ARM compile receipt, or `--sanitize` with a host
target. The recipe refuses to overwrite an existing directory.
