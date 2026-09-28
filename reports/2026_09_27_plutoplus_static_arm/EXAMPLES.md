# Saved-file examples on 192.168.1.15

After connecting by SSH, use the existing mounted SD directory below.
After reboot, mount the existing filesystem as described in RUNBOOK.md.
These commands read saved IQ and print JSON; they do not access RF hardware.
Each executable pins and verifies CPU0, processes both receivers serially,
performs one warmup and five measurements, and has a 15-second alarm.

```sh
cd /mnt/glrtbench/leo-static-glrt.4jwvdm

# 2.5 MS/s
./D case-024.ci16 2500000-lower-exact.c128 2500000-lower-control.c128 2500000 lower seq-dev-r2500000-scan-fw-1a0e881391ba1d2f-v001678

# 5 MS/s
./D case-056.ci16 5000000-upper-exact.c128 5000000-upper-control.c128 5000000 upper seq-dev-r5000000-scan-fw-3ec1c634e1f48f77-v000446

# 7.5 MS/s
./D case-088.ci16 7500000-lower-exact.c128 7500000-lower-control.c128 7500000 lower real-dev-r7500000-scan-fw-247bd59bd5950cb1-v001452

# 10 MS/s
./D case-096.ci16 10000000-upper-exact.c128 10000000-upper-control.c128 10000000 upper real-dev-r10000000-scan-fw-4fc9ccc9f49e637b-v001511
```

Replace ./D with ./A for the packed/FP64 baseline, ./B for packed/FP32,
or ./C for natural-stride/FP64. Keep all remaining arguments identical.
For the latest qualified optimized build, replace `./D` with
`./opt-goal40mag` in each of the four examples. That executable is already
on the SD card; see [the 40% headroom report](optimize/GOAL40.md) for its
binary hash, scientific qualification and concurrent measurements.
For reproducible comparisons across the complete cohort, use run_target.py
through RUNBOOK.md; it rotates method order, verifies hashes and evaluates
the scientific gates. Individual example invocations are smoke checks.

The manifest in the reproduction directory records source paths and hashes.
Rate-specific template geometry is required; do not relabel an input's rate.
