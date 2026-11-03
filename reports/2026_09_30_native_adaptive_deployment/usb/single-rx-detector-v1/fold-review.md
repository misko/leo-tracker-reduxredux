# Single-receiver fold parity review

Date: 2026-09-30

Result: pass. This component regression was added after review found that the
first single-receiver NEON implementation scalarized a four-sample lag tail and
then briefly mapped lag-3/lag-5 scalar tails through lag 1. The corrected helper
preserves the established dual-receiver vector/tail schedule and passes bitwise
comparisons against each extracted dual receiver.

## Coverage

`tests/native_adaptive/detector/test_single_rx_fold.c` compiles the actual
private proposal implementation into a standalone component test. It covers:

- receiver 0 and receiver 1 extracted independently from IQIQ input;
- lags 1, 3, and 5 with every independent valid-length combination from 0
  through 9;
- two start/offset pairs;
- signed-16 extrema and deterministic patterned samples;
- unchanged input buffers and untouched output tails;
- 8,000 scalar comparisons on every target, plus 8,000 production NEON
  comparisons on ARM.

This is arithmetic and input-mapping evidence. It is not detector throughput,
candidate parity over DS9, RTL-SDR hardware, RF, or Raspberry Pi qualification.

## Frozen closure

| Item | SHA-256 |
| --- | --- |
| `tests/native_adaptive/detector/test_single_rx_fold.c` | `6eceaef5af70734811dd2e1e8242ba0e447ffaecfd09b0d6ed6c9f526192075c` |
| `native/adaptive/detector/kernel/private/proposal_core.c` | `95e56bb1ae5b949e7917cda3b099cc5138e7124bef6d864f9400771b9166074b` |
| `native/adaptive/detector/kernel/private/dwell_input.h` | `81fb39b6c1665e5693edcb24739c58f1ffd5a5ea2517731b1c44157bdb6aed7e` |
| Host binary | `f63d0ff57391c5943398ce300c8e8cd5689ec724ecbfa30656fde8905673cf42` |
| ASAN/UBSAN binary | `a46089592fd2c699987e32a7e7c483668e21f061df50ffb03456f269bb4d5e80` |
| ARM binary | `f91468582d8244e3a84f42dd8574e1a9ab7111a90e5139ad68dd4d60bfa5feeb` |
| Host log | `f0aa1c75899a8338cc0189fc5442bdce8225d5cf5173cacb8e4b77b68599a85c` |
| ASAN/UBSAN log | `d9701b7e384f206503cbbd30cf25821522451c443b551959b102ba8e6ce1955f` |

Host production flags passed in less than 0.01 seconds at 2,112 KiB maximum
RSS. ASAN with leak detection and UBSAN passed in 0.02 seconds at 8,268 KiB.
The physical ARM CPU-only run passed in 0.106153639 seconds at 1,012 KiB; see
[the physical receipt](physical-arm/fold.json) and
[log](physical-arm/fold.log).

## Rebuild commands

Run from the repository root. These commands intentionally compile the private
proposal source through the test translation unit and do not link the detector
archive.

```bash
defines=(
  -DCONDITIONED_MOMENT_BLOCK=64 -DLEO_PRESENCE_FFTW=1
  -DLEO_PROPOSAL_LIBRARY -DLEO_PROPOSAL_OMIT_POWER=1
  -DLEO_NEON_CONDITIONED_MOMENTS=1 -DLEO_TRACK_MIN_MATCHES=1
  -DLEO_PROPOSAL_FRAME_BUDGET=8 -DLEO_PROPOSAL_FFT_DIVISOR=2
  -DLEO_FINE_FRAME_BUDGET_DEFAULT=2 -DLEO_DETECTOR_THREAD_CPU=1
  -DSKIP_CONDITIONED_RECHECK=1
  -DLEO_PRESENCE_COARSE_CI16_FIXED_SCALE=1
  -DLEO_PRESENCE_COARSE_FP32 -DLEO_FULL_CONDITIONED_SCREEN
  -DLEO_FULL_REFINEMENT_MODE=2
)
includes=(
  -I native/adaptive/detector -I native/adaptive/detector/kernel
  -I native/adaptive/detector/kernel/private
  -I native/adaptive/detector/kernel/private/native_presence
)
base=(
  -std=c11 -Wall -Wextra -Werror -fno-fast-math -fno-math-errno
  -fno-trapping-math -fcx-limited-range -fPIC
)

TMPDIR=/var/tmp/leo-single-rx-fold-host-v3-tmp cc "${base[@]}" -O3 \
  "${defines[@]}" "${includes[@]}" \
  tests/native_adaptive/detector/test_single_rx_fold.c \
  /usr/lib/x86_64-linux-gnu/libfftw3f.a -lm \
  -o /var/tmp/leo-single-rx-fold-host-v3/test-single-rx-fold
/var/tmp/leo-single-rx-fold-host-v3/test-single-rx-fold

TMPDIR=/var/tmp/leo-single-rx-fold-sanitize-v3-tmp cc "${base[@]}" \
  -O1 -g -fno-omit-frame-pointer -fsanitize=address,undefined \
  "${defines[@]}" "${includes[@]}" \
  tests/native_adaptive/detector/test_single_rx_fold.c \
  /usr/lib/x86_64-linux-gnu/libfftw3f.a -lm \
  -o /var/tmp/leo-single-rx-fold-sanitize-v3/test-single-rx-fold
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  /var/tmp/leo-single-rx-fold-sanitize-v3/test-single-rx-fold

arm_cc=/home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc
TMPDIR=/var/tmp/leo-single-rx-fold-arm-v3-tmp "$arm_cc" "${base[@]}" -O3 \
  -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard \
  -DLEO_PROPOSAL_NEON_FOLD "${defines[@]}" "${includes[@]}" \
  -I /var/tmp/leo-fftw-float-20260912/install/include \
  tests/native_adaptive/detector/test_single_rx_fold.c \
  /var/tmp/leo-fftw-float-20260912/install/lib/libfftw3f.a -lm \
  -o /var/tmp/leo-single-rx-fold-arm-v3/test-single-rx-fold
```

The ARM build is an ELF 32-bit little-endian ARM EABI5 executable using the
Cortex-A9 hard-float NEON path. Root performed the physical CPU-only execution;
this review did not access hardware.
