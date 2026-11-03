# Support geometry experiment

`protocol.json` fixes the control/optimized/optimized/control order and input
digest. `payloads.json` records device executable hashes. `comparison.json`
contains measured CPU/wall/RSS and checks all 16,191 rows for exact equality.
Input epochs come from passing candidates (margin >= 0.025) in
`../recorded-graph-v1/output.jsonl`, preserving visit and candidate order.

Build each preserved runtime source with the repository's
`native/adaptive/runtime/integer_support_cli.cpp` and runtime include directory:

```sh
arm-linux-gnueabihf-g++ -std=c++17 -O2 -fno-fast-math -ffp-contract=off \
  -pthread -mcpu=cortex-a9 -mfpu=neon -mfloat-abi=hard \
  -static-libstdc++ -static-libgcc -Inative/adaptive/runtime \
  RUNTIME_SOURCE native/adaptive/runtime/integer_support_cli.cpp -o EXECUTABLE
```

The compiler used was the PLUTO firmware Buildroot host toolchain. Executables
and input were staged under `/mnt/glrtbench/support-geometry-hoist-v1/`.
Each trial ran locally on ARM with:

```sh
/mnt/glrtbench/native-adaptive/current/measure-run 90 EXECUTABLE < inputs.tsv
```

The control and optimized runtime sources are preserved here. This is a
support-only recorded-data diagnostic. No RF was collected and no scientific
fixtures were changed. A new complete detector/projection replay remains
necessary to measure the end-to-end effect.
