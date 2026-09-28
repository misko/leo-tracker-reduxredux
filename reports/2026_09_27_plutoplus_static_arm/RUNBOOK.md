# Saved-file development on PLUTO+ 192.168.1.15

## Target setup

The user authorized formatting the attached SD card. The existing single
32-MiB-aligned partition was retained, changed to Linux type 83, and formatted
with the firmware's BusyBox mke2fs as ext2, 4096-byte blocks, 262144 bytes per
inode, zero reserved percentage, label GLRTBENCH. It is mounted with noatime
at /mnt/glrtbench and reports 238.1 GiB available immediately after formatting.
No firmware, RF, capture configuration or system service was changed.

The root filesystem is ephemeral. After a reboot, recreate the mount point
and mount the already formatted card; **do not repeat formatting**:

```sh
mkdir -p /mnt/glrtbench
mount -t ext2 -o noatime /dev/mmcblk0p1 /mnt/glrtbench
```

The SSH host key changes on every boot, as confirmed by the user. Pin that
boot's key in a private experiment known_hosts file. Authentication uses an
existing password file passed to sshpass with -f, never printed or embedded
in a command line. The runner also supports existing SSH key authentication
by omitting --password-file. Only 192.168.1.15 is accepted by this runner.

## Compile on the host, execute on ARM

The target has no gcc or Python. Use the existing Buildroot cross-compiler:

`/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc`

The build uses Cortex-A9, NEON, hard-float, the existing scientific profile,
and four matched input/backend combinations. No threaded FFTW is linked.
The FP32 archive is linked privately/static; the FP64 FFTW library is staged
beside the executables and resolved by $ORIGIN. Target libc is 2.25.
The ARM executable sets and verifies one-core affinity before initialization
and arms a 15-second alarm. Both receivers execute serially on CPU0.

From the repository root, for a new output directory:

```sh
PYTHONPATH=src .venv/bin/python reports/2026_09_27_plutoplus_static_arm/experiment.py prepare /tmp/leo-arm15-new
PYTHONPATH=src .venv/bin/python reports/2026_09_27_plutoplus_static_arm/experiment.py build /tmp/leo-arm15-new
PYTHONPATH=src .venv/bin/python reports/2026_09_27_plutoplus_static_arm/experiment.py asan /tmp/leo-arm15-new
PYTHONPATH=src .venv/bin/python reports/2026_09_27_plutoplus_static_arm/host_check.py /tmp/leo-arm15-new
PYTHONPATH=src .venv/bin/python -m pytest -q reports/2026_09_27_plutoplus_static_arm/test_experiment.py
```

Preparation exports 104 cases: 80 real visits and 24 controls. All four native
rates have real examples, both receivers and controls. It verifies original
NumPy hashes and emits header-free CI16 plus rate-specific exact/control
templates. The IQ payload is roughly 0.5 GB; do not duplicate it unnecessarily
across builds. No QNAP write or RF access is used.

The completed build inputs and binaries for this experiment are preserved in
build-snapshot.tar.gz. It contains source snapshots, four ARM executables,
private FFTW library, profile, build receipt and data manifest; original IQ is
referenced by manifest rather than duplicated in the archive. Sources in the
other repositories are read-only build inputs, never runtime dependencies.

Run on the hardware after the host controls pass:

```sh
PYTHONPATH=src .venv/bin/python reports/2026_09_27_plutoplus_static_arm/run_target.py \
  --host 192.168.1.15 \
  --bundle /tmp/leo-arm15-new \
  --output reports/2026_09_27_plutoplus_static_arm/target_run_new \
  --known-hosts /absolute/path/to/current-boot-known-hosts \
  --password-file /absolute/path/to/existing-password-file \
  --rates 2500000 5000000 --max-seconds 600
```

Then run a separate output directory with `--rates 7500000 10000000
--max-seconds 420`. These phases contain 76 and 28 cases respectively, retain
all controls, and do not require duplicating the host bundle. The initial
all-rate 850-second run stopped during its final case; do not overwrite that
incomplete receipt or extend its deadline. A separate 180-second rerun of all
eight real 10-MS/s visits completed the original comparison. Rate-group support
was added afterward; exact original runner/evaluator copies are saved in each
target_run directory beside their source hashes.

This command is explicitly a hardware experiment; ordinary pytest tests do not
connect to hardware or silently skip a hardware dependency. Password-file use
requires the configured noninteractive sudo access; key authentication does not.
The target session is bounded to 850 seconds plus a ten-second final sync.
Each rate runs controls before real cases. A scientific failure ends that rate,
and its incomplete cohort cannot be promoted. Other rates remain independent.

## Output and repeatability

run-lock.json identifies the unique /mnt/glrtbench/leo-static-glrt.* directory.
It retains binaries, templates, raw IQ and per-case JSON results for further
development. On the host, target_run_* contains matching raw receipts, stderr
with core/PID evidence, source/build hashes, target metadata, per-case
assessments, summary and completion status. Transfer and file reading are
separate from the resident-IQ detector timing. SD bandwidth is not included
in the claimed compute speedup. Neither are startup and FFT planning.

Read summary.json by rate and split; compare sums of paired per-case median
CPU, never a ratio of unpaired averages or a multiplication of separate gains.
All times cover both receivers serially unless explicitly labeled otherwise.
Treat small-cohort p95/max values as descriptive, not a field service guarantee.

## High-rate implementation findings

Simply removing the old 2.5/5-MS/s admission guard was unsafe. The isolated
snapshot also needs:

1. Coarse reference and rotated scratch capacity for up to 45 samples/symbol.
2. Fine-frequency/score arrays of 2048 elements, with a geometry admission
   bound (7.5 MS/s needs more than the old 1602 elements).
3. Input scratch sized for the actual fine FFT. At 7.5 MS/s its radix-2 size
   is 16384, larger than the old rate/500 allocation of 15000.

Host ASan/UBSan exposed the second and third issues before target execution.
The final host run passes all 24 controls through all four variants (96
method/case executions, each with warmup and five measured calls).
These are research-only source copies. Production detector code and frozen
scientific fixtures were not edited.
