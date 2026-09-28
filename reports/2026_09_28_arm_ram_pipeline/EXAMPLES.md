# Reproduce the saved-IQ ARM RAM experiment

Run from the repository root. The preparation step requires the sealed DS7
cache and qualified native source trees referenced by `prepare.py`. The host
build additionally needs GCC and float FFTW. The ARM build uses the existing
Buildroot Cortex-A9 toolchain. No compilation occurs on the PLUTO+.

Use a new output directory for each experiment:

```sh
.venv/bin/python reports/2026_09_28_arm_ram_pipeline/prepare.py prepare --output /var/tmp/leo-arm-ram-next
.venv/bin/python reports/2026_09_28_arm_ram_pipeline/prepare.py build --output /var/tmp/leo-arm-ram-next
.venv/bin/python -m pytest -q reports/2026_09_28_arm_ram_pipeline
.venv/bin/python reports/2026_09_28_arm_ram_pipeline/run_target.py --prepared /var/tmp/leo-arm-ram-next --output reports/2026_09_28_arm_ram_pipeline/run-next
```

The runner stages and verifies files in a unique directory on the SD card of
192.168.1.15. It runs all four rates, both native implementations, isolated
analysis, and two concurrent arrival schedules. It does not access a radio,
change affinity of other services, or format storage. Existing SSH credentials
and the development-only known-hosts file are reused without logging secrets.

For individual examples, enter the staged directory's `data` subdirectory on
the PLUTO+. The following run the optimized worker with CPU0 analysis, CPU1
RAM production, both receivers, and a three-slot ring:

```sh
../arm-goal40mag cases-2500000.txt 2500000 120 120 0 1 2 3
../arm-goal40mag cases-5000000.txt 5000000 60 120 0 1 2 3
../arm-goal40mag cases-7500000.txt 7500000 60 120 0 1 2 3
../arm-goal40mag cases-10000000.txt 10000000 60 120 0 1 2 3
```

Use producer core `-1` for isolated resident-input analysis. To use the
source-counter cadence at 2.5 MS/s:

```sh
head -n 120 counter-arrivals-2500000.txt > active-offsets.txt
../arm-goal40mag cases-2500000.txt 2500000 120 120 0 1 2 3 active-offsets.txt
```

Arrival files must contain exactly the requested number of offsets. The same
pattern applies to each higher rate using its own file and job count. Each
process has a 120-second alarm. Run phases sequentially and avoid simultaneous
SD transfers or other benchmarks. Preserve JSONL output, including its terminal
receipt: process completion alone does not establish zero drops or capacity.

These examples exercise the existing rank-six/confirm-one native detector.
They do not establish recovery of individual detections from the full server
GLRT search. RAM replay also does not model real DMA, interrupt, IIO, or adaptive
capture-processing overhead.
