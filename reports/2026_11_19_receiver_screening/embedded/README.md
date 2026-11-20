# Compact orbital projection on Arm

The receiver's C orbital projector produced the same bytes on native x86-64 and on emulated Cortex-A9 and AArch64 across **5,023,812 satellite-time cells** from two recordings. The Arm executables are statically linked. The Cortex-A9 build uses the Pluto firmware toolchain and ARMv7 EABI5 hard float. Both Arm runs used QEMU user mode on the corpus host. [Protocol](PROTOCOL.md) · [DS26 receipt](DS26-0036.json) · [DS29 receipt](DS29-0082.json)

The input contains the original orbit bank, every distinct track observation time and the supplied search center for each archived recording. The test projects one coordinate at zero orbit phase, with the original 0.05 s finite-difference step. It exercises all satellites on the initial grid. Its RF reference is the projector's nominal scale. Calibration arms and position selection begin outside this boundary. The frozen NumPy implementation supplies the comparison values. [Frozen archive preparation](../../../tools/pipeline_eval/qualification/projector_audit.py) · [C projector](../../../tools/pipeline_eval/variants/orbit_projector.c)

| Recording | Satellites × observation times | Maximum Doppler difference | Maximum elevation difference | Maximum phase-derivative difference |
|---|---:|---:|---:|---:|
| DS26-0036 | 1,524 × 2,053 | 1.162 × 10⁻⁸ Hz | 1.781 × 10⁻¹⁰° | 7.422 × 10⁻¹⁰ Hz/s |
| DS29-0082 | 1,680 × 1,128 | 7.334 × 10⁻⁹ Hz | 5.814 × 10⁻¹¹° | 2.728 × 10⁻¹⁰ Hz/s |

## Memory boundary

The original reference retains eight prepared NumPy arrays and returns three output arrays. The C harness holds five prepared arrays and the three output arrays in one allocation. The compiler reports 320 bytes for the Cortex-A9 projection function's stack frame and 256 bytes for AArch64. The table counts the simultaneously live named arrays at projection return. Transient reference calculations, input preparation, runtime buffers and physical peak RSS lie outside this accounting. [Standalone ABI and allocation checks](../../../tools/pipeline_eval/qualification/projector_archive_arm.c)

| Recording | Reference prepared | Compact prepared | Same three outputs | Reference → compact live arrays |
|---|---:|---:|---:|---:|
| DS26-0036 | 381.93 MiB | 23.46 MiB | 71.61 MiB | 453.54 → 95.08 MiB, 4.77× lower |
| DS29-0082 | 231.33 MiB | 25.81 MiB | 43.37 MiB | 274.70 → 69.19 MiB, 3.97× lower |

The local USB inventory showed an attached Pluto SDR. Its idle state and a scratch-only execution path could not be established, so the device was left untouched. The previous physical Pluto+ reported 506,568 KiB of RAM, while the earlier x86 compact-v5 worker reached 1,389,240 KiB peak RSS. The new proof covers the projector's binary and data interface. Physical kernel timing, concurrent receiver memory, and full v5 on the device remain unmeasured. [Earlier physical timing and host memory receipts](../../2026_11_19_receiver_frontend/embedded/README.md)

## Reproduce

Run from the repository root on the corpus host with the Pluto toolchain, `aarch64-linux-gnu-gcc`, `qemu-arm` and `qemu-aarch64`. The fixture generator uses the bound original v5 archive and writes only to the selected working directory. It emits static executables, a packed input fixture, and raw output arrays for each target. [Replay runner](../../../tools/pipeline_eval/qualification/projector_archive_arm.py)

```sh
out=$(mktemp -d)
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
for case_id in DS26-0036 DS29-0082; do
    taskset -c 6 .venv/bin/python -m tools.pipeline_eval.qualification.projector_archive_arm \
        --case "$case_id" --work "$out/$case_id" --out "$out/$case_id.json" || exit
done
```

The standalone Cortex-A9 program accepts the generated `stencil.bin` over standard input. On an approved, idle Armv7 Linux board, place the binary and fixture in its designated scratch area. Stream the output to `sha256sum` to avoid storing the output arrays a second time. The digest should equal the selected receipt's `raw_sha256`. The JSON printed to standard error gives the named array bytes and allocation count.

```sh
./projector < stencil.bin | sha256sum
```
