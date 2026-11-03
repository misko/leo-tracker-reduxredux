# Sidecar ARM decision artifacts

These binaries are a reproducible cross-build of the isolated
`source/sidecar.cpp` tracking experiment. They are intended only for the
root-owned bounded ARM comparison against the already frozen dense candidate.
They do not modify production and have not been run on the device by this
component agent.

The sidecar removes `Point::source_group_index` and moves the immutable
point-to-group indexes into the lane-local `SourceWorkspace`. Selection,
fallback-key collision behavior, lexical group order, rank order, floating
point operations and workspace lifetime are otherwise identical to the frozen
dense candidate.

The build used Linaro GCC 7.3.1 for `arm-linux-gnueabihf` with:

```text
-std=c++17 -O3 -fno-fast-math -fPIC -mcpu=cortex-a9 -mfpu=neon
-mfloat-abi=hard -Wall -Wextra -Wpedantic -pthread
-static-libstdc++ -static-libgcc
```

Reproduce from the report root with:

```sh
bash build.sh arm sidecar /var/tmp/leo-dense-source-sidecar-arm
```

Prior host qualification is bound in `receipt.json`: the focused differential
test passes, and all 60 five-second causal prefixes serialize byte-identically
to the frozen dense candidate. The ten-run shared-host diagnostic found warm
performance effectively tied and sidecar cold performance 1.386% faster. That
host timing is evidence for deciding whether to run ARM; it is not an ARM
performance result.

Root-owned physical ARM qualification completed after the cross-build. The
focused test passed in 3.915 seconds wall time. Serial candidate/sidecar/
sidecar/candidate prefix measurements all reported two bit-exact prefixes and
64 final tracks. The frozen dense candidate averaged 15.07866 seconds warm and
23.46999 seconds cold; the sidecar averaged 14.74366 seconds warm and 21.56645
seconds cold, reductions of 2.222% and 8.111%. No timed processes overlapped
and no RF was used. A separate complete sidecar reconstruction emitted the
expected 676,954-byte output with SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`
in 22.099 seconds wall time.

Full sidecar ASAN/UBSAN reconstruction and the existing public
`LaneExecution` test linked to the sidecar under TSAN both pass with empty
sanitizer output. The independent review found no source correctness or
ownership blocker.

With the authoritative candidate fixture staged beside the binaries, the
bounded decision commands are:

```sh
./prefix candidates.tsv 5 100663296 --tail-two
./tracking candidates.tsv
```

The prefix command must report two bit-exact prefixes. The full tracking
stdout must hash to
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`,
the already verified host/view/candidate public output. Timing comparison uses
the prefix command; the full command is a separate scientific parity check.
