# Offline wide detector build

The standalone builder reproduced both published ABI-1 wide detector libraries byte-for-byte with the measured GNU/FFTW toolchain. It builds the original **21-bin ±800 kHz** detector and the **adjacent-sample batch** from a local authenticated source capsule. Both builds keep the four proposed time regions. [Build and replay receipt](offline-check.json) · [Measured kernel study](../wide-kernel/README.md)

## Build

Use Python 3.10 or newer, GCC with `gcc-ar`, the native GNU linker and development files for FFTW. On Debian and Ubuntu the build packages are `build-essential` and `libfftw3-dev`. The builder uses the Python standard library. For a local FFTW distribution pass `--fftw-prefix /path/to/fftw` with `include/fftw3.h`, `libfftw3f.a` and `libfftw3.so` in a conventional library directory. Install the matching shared double-precision FFTW runtime or set its loader path when using a custom prefix.

```sh
python -m tools.pipeline_eval.wide_runtime --out /var/tmp/leo-wide-local
```

For a standalone copy, put these two files together and run `python -I wide_runtime.py --out /var/tmp/leo-wide-local`. The output directory must be new. `--variant stock` or `--variant adjacent` builds just one. [Builder](../../../../tools/pipeline_eval/wide_runtime.py) · [Source capsule](../../../../tools/pipeline_eval/wide_runtime_source.zip)

Each variant contains `libleo-adaptive-detector.so`, `leo-native-glrt-short-window` and a build receipt. Here is the short-window command for the adjacent batch variant.

```sh
/var/tmp/leo-wide-local/adjacent/leo-native-glrt-short-window \
  --rate-hz 10000000 --fractional-epoch \
  --exact-template exact.c128 --control-template control.c128 --input-ci16 visit.ci16
```

For this invocation each template is a little-endian complex128 frame with 13,333 samples. `visit.ci16` is one contiguous 20 ms dual-RX window, with little-endian int16 in `[time, receiver, I/Q]` order. The result contains native detector candidates. The measured optimization uses AVX2 when available and keeps the original per-output path otherwise.

## Evidence

The capsule is 80,344 bytes and contains 29 translation-unit or header dependencies, the original build recipe, the original license and provenance records, the two-file adjacent-batch overlay and a SHA-256 manifest. The builder verifies the complete capsule and every member before use. It preserves the archived source license record, including its statement about the original repository's license status. The toolchain and FFTW are workstation dependencies.

An ext4 build ran in Bubblewrap with a separate network namespace and only the copied capsule, system toolchain and temporary workspace visible. `/srv/bulk`, the repository, and the earlier `/tmp` FFTW/build locations were absent. GCC 15.2.0 and the system FFTW 3.3.10 files matched the archived dependency hashes. Both shared libraries and both short-window executables reproduced their archived hashes. A local FFTW prefix referencing the same package files also rebuilt the adjacent library exactly. Other toolchain versions have their own output hashes in `release.json`.

The rebuilt libraries also reproduced all public detector fields on two authentic saved visits, one per sideband, and ten recorded synthetic controls covering weak, signed edge, empty and seeded Gaussian IQ. Those payload checks used the existing replay harness after compilation. The scope is build and detector parity. [Original stock build](../../receiver-core/cfo-stride/control-build.json) · [Original adjacent build](../wide-kernel/build-receipt.json) · [Payload and dependency hashes](offline-check.json)

The isolated build can be repeated on a local ext4 volume with this command from the repository.

```sh
scratch=$(mktemp -d /var/tmp/wide-runtime.XXXXXX)
cp tools/pipeline_eval/wide_runtime.py tools/pipeline_eval/wide_runtime_source.zip "$scratch/"
bwrap --unshare-net --clearenv --ro-bind /usr /usr \
  --symlink usr/lib /lib --symlink usr/lib64 /lib64 --symlink usr/bin /bin \
  --proc /proc --dev /dev --tmpfs /tmp --bind "$scratch" /work \
  --setenv PATH /usr/bin:/bin --setenv LANG C.UTF-8 --chdir /work \
  /usr/bin/python3 -I -B /work/wide_runtime.py --out /work/release
```
