# Reproduction

Run from the repository root with the project Python environment and
`PYTHONPATH=src`. Python analysis requires NumPy and Matplotlib. Native host
tests require GCC, FFTW and the dependencies documented by their component
tests. Hardware replay requires the existing saved corpus, templates, ARM
toolchain/FFTW artifacts, and SSH access; it never requests RF capture.

## Evidence without hardware

`evidence.tar.gz` contains measured JSONL, manifests, compiler profiles and the
176 selected frozen-original oracle rows. It contains no IQ or credentials.
`evidence-manifest.json` hashes every member and the original full oracle file.
Extract it into this report directory to restore the ignored `local/` tree:

```sh
report=reports/2026_09_29_arm_sparse_headroom
tar -xzf "$report/evidence.tar.gz" -C "$report"
PYTHONPATH=src python "$report/summarize.py" \
  --baseline "$report/original-selected.jsonl" \
  --labels fullprep-uncached sparse-uncached sparse-cached sparse-cached-pgo \
    sparse-tiled sparse-tiled-reuse-pgo sparse-reuse-plans sparse-reuse-plans-pgo33
PYTHONPATH=src python "$report/stress.py" summarize --label final-stress
PYTHONPATH=src python "$report/render.py"
```

The first label is the exact current-native authority; preserve its order.
The selected oracle has the same scientific rows but a different whole-file
hash from the full original oracle used to publish `comparison.json`; that
metadata hash is the expected difference on this replay. The stride matcher
and diagnostic projection adapter are imported from the adjacent published
`2026_09_29_arm_strides` report. They are analysis tools, not the native runtime.
Quantiles use nearest rank except the median. Cold CLI canonicalization only
normalizes its existing integer `glrt_complete` to the benchmark's Boolean;
it never drops candidate fields or changes numeric scores.

## Build the maintained component

The selected receipts are
[`builds/final-v3/build-receipt.json`](builds/final-v3/build-receipt.json) and
[`builds/pgo-v3/use-build-receipt.json`](builds/pgo-v3/use-build-receipt.json).
They record every compiler/link command, compiler and archiver identity,
FFTW hashes, source closure, profile inputs and output hashes. The device's
shared FP64 FFTW hash is in `device-before.txt`. `final-source-manifest.json`
binds the final source archive; earlier snapshots preserve measured ablations.

Example ordinary build, using the paths of the measured toolchain:

```sh
PYTHONPATH=src python -m leo.qualification.arm_glrt_release \
  --source-root "$PWD/src/leo/analysis/native_glrt" \
  --output-dir /var/tmp/glrt-replay-normal \
  --work-dir /var/tmp/glrt-replay-normal-work \
  --compiler /home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc \
  --archiver /home/mouse9911/gits/plutosdr-fw/buildroot/output/host/bin/arm-linux-gnueabihf-gcc-ar \
  --fftw-prefix /var/tmp/leo-fftw-float-20260912/install \
  --target arm-cortex-a9 --with-benchmark
```

Use the receipt's exact paths and commands when reproducing binary hashes;
an equivalent rebuild at different paths is not promised byte-identical.
No fast-math or newly reduced precision is introduced. The normal build is
sufficient to reproduce a passing matched panel; PGO is optional.

For the final PGO build, generate and use **the same absolute work directory**
`/var/tmp/leo-native-glrt-headroom-pgo-work-v3` and profile root
`/tmp/leo-native-glrt-headroom-pgo-profile-v3`. The generate/use receipts specify
the complete commands. Either restore `local/pgo-training-v3/profiles.tar`
under `/tmp` (archive members begin with the profile-root basename), verifying
all six `.gcda` hashes against `builds/pgo-v3/profile-manifest.json`, or train a
fresh generate build using:

```sh
python "$report/train_pgo.py" --build /path/to/generate-build \
  --password-file /path/to/existing-ssh-secret \
  --profile-dir /tmp/leo-native-glrt-headroom-pgo-profile-v3 \
  --label pgo-training-v3 --include-tail \
  --training-panel "$report/pgo-training-panel-v3.json"
```

Use a clean profile directory for fresh training. This panel is 33 contexts,
including the measured clipped-grid outlier; it is not the earlier random
32-context panel. Training executes 33 CLI and 132 persistent calls on saved
data. Missing profiles are build errors. Never combine old and new profiles.

## Physical replay

`panel.json` identifies the source contexts; `execution-panel.json` binds all
staged CI16/template hashes and shuffled call sequences. Original saved-input
sources were `/var/tmp/leo-ds7-large-arm-20260928` and
`/var/tmp/leo-arm-full-search-oracle-allrates`. To restage those same sources:

```sh
python "$report/execute.py" stage \
  --password-file /path/to/existing-ssh-secret \
  --inputs /var/tmp/leo-ds7-large-arm-20260928 \
  --oracle /var/tmp/leo-arm-full-search-oracle-allrates
python "$report/execute.py" run \
  --password-file /path/to/existing-ssh-secret \
  --binary /path/to/build/leo-native-glrt-bench \
  --receipt /path/to/build/build-receipt.json --label fresh-replay
```

The default target is `root@192.168.1.15`; SSH boot-key changes are deliberately
accepted for this development device. Do not put the password in the report.
Use a fresh output label: existing completed groups are resumed, not replaced.
The maintained C client preloads saved IQ, creates one context per batch,
pins CPU0 and invokes the public RAM API. It processes dwells serially.

The frozen `stress-plan.json` selects 16 slowest upper-edge control contexts,
100 shuffled repeats in one process, plus five separate fresh-process checks:

```sh
python "$report/stress.py" run --label fresh-stress \
  --password-file /path/to/existing-ssh-secret \
  --binary /path/to/build/leo-native-glrt-bench \
  --cli /path/to/build/leo-native-glrt \
  --receipt /path/to/build/build-receipt.json
python "$report/stress.py" summarize --label fresh-stress
```

Do not regenerate the stress plan after seeing optimized timing. Device
`time -p` measures fresh-process CLI time; SSH transport is excluded. Saved
files may be page-cached. All detector timings include the public call's
allocation/preparation/search/cleanup; persistent-client timing adds telemetry
and output but still excludes preload/setup. Capture and queueing are absent.

## Tests and gate

```sh
PYTHONPATH=src:/var/tmp/leo-strides-pinned-pluto-dependency/src python -m pytest -q \
  tests/contracts/test_arm_glrt.py tests/analysis/test_native_glrt*.py \
  tests/qualification/test_*glrt*.py tests/cli/test_arm_glrt_cli.py \
  reports/2026_09_29_arm_sparse_headroom/test_summarize.py
```

The additional pinned source path supplies the existing CLI's `pluto-utils`
dependency, not an oracle/runtime dependency of the native detector. See
[VALIDATION.md](VALIDATION.md) for sanitizer commands and all-geometry checks.
The preferred gate is **both detector CPU and wall maxima ≤100 ms**, with
p95/max below 120 ms, exact current-native candidates/counters, and no observed
repeated-call instability. The matched normal/PGO panels and sustained PGO
test pass. A finite panel is not a universal hard-real-time guarantee.
