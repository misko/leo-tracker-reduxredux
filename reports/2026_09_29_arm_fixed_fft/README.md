# Experimental ARM fixed-point fine FFT

This experiment replaces only the cached fine FFT with a genuine integer
mixed-radix transform.  Transform lengths, bin mapping, frequency grid, energy
normalization, score accumulation, winner selection, and interpolation remain
unchanged.  The scorer is FP64.  There is no fallback in the selected raw mode.

Complex values are packed signed 16-bit lanes.  Products widen before
accumulation.  Radix-2/3/5 stages divide by their radix, producing an exact
declared block scale of `N`; dynamic input packing restores the unnormalised
FFT amplitude.  Packing, scale selection, root planning, execution and storage
all occur within the existing search lifetime.  Q15 is the candidate.  `--q7`
is calibration-only and produces a separately identified build.

`python build.py` creates and tests a new immutable host snapshot derived from
`arm_fine_precision/builds/host-raw-v2`.  `python build.py --sanitize` makes the
sanitizer snapshot; `python build.py --arm` cross-builds from `arm-raw-v2` but
does not run ARM code.

## Publication bundle and reproduction

The `receipts/` directory contains the compact measurement records for the
initial host v1 experiment, the packed-DSP host v6 experiment, and the final
ARM v7 experiment.  Each record includes the build receipt, evaluation
manifest, timing/science summary, and standard-hit audit.  IQ inputs, row-level
outputs, executables, and repeated build-tree snapshots are intentionally not
included.

`measured-sources.tar.gz` is the exact source population named by those three
build receipts.  It is content-addressed, so a source shared by multiple builds
occurs once.  `measured-sources-index.json` maps each measured build and source
path to its SHA-256 object name.  To inspect or reconstruct one snapshot:

```sh
tar -xzf measured-sources.tar.gz
# For each snapshots[BUILD].files[PATH] entry in measured-sources-index.json,
# copy measured-source-objects/SHA256 to PATH.
```

To rebuild the final code in the full repository, retain the immutable
`reports/2026_09_29_arm_fine_precision/builds/{host,arm}-raw-v2` baselines and
run `python3 build.py`, `python3 build.py --sanitize`, or
`python3 build.py --arm`.  The generated `fixed-fft-build.json` records compiler
commands, binary hashes, source hashes, and unit-test output.  ARM execution is
separate: run the cross-built `test_fixed_fft` on the PLUTO target before the
cohort evaluator.  `SHA256SUMS` authenticates every staged publication file.
