# Portable original candidate verifier

The standalone C verifier processed **112 candidates from six authenticated stereo visits** on native x86-64, emulated Cortex-A9 and emulated AArch64. All three builds matched the original fine and conditioned CFO winners, integer and fractional GLRT CFO bins, bracket status, and ordered physical candidate gates. Of 112 candidates, 64 resolved a fractional epoch, 19 passed the fractional margin gate and 48 were unbracketed. Every final published factor matched its independent recording archive within the declared numeric bounds. [Manifest and full outputs](manifest.json) · [Protocol](PROTOCOL.md)

The CLI takes exact and symbol-rolled pilot templates for the recorded edge, full dual CI16 IQ, and the retained refined epoch and fine-grid bounds for each candidate. Its C path performs fine CFO folding and interpolation, whole-frame conditioned CFO with direct contender checks, and held-pilot acquisition ranking. It computes exact and rolled GLRT at five circular integer epochs, fits the bracketed log peak, then recomputes both continuous scores with normalized Lanczos interpolation. The static executable uses C and the math library, with the existing portable fine transform, conditioned moments, GLRT correlation and binary64 FFT kernels. Precomputed template and seed groups are input files. Coarse acquisition, peer-route policy, position fitting and full scanner timing are outside this measurement.

The closest archived lower-edge fractional pass was **0.025002313685** on DS26-0237 visit 1561, receiver 1. The closest lower-edge fail was **0.024928365588** on visit 3235. The nearest measured upper-edge pass was **0.025063875350** on DS29-0082 visit 5855. No-pass visits and flat IQ retain the expected fail or unbracketed result. The DS29-0519 visit 153 equivalent tie retained seed order. On DS26-0237 visit 3235, two marked score-equivalent seeds swapped provenance positions. They resolved to the same epoch and their reference CFOs differed by 7.73 × 10⁻¹² Hz. Final physical candidate order and gates agreed at those ranks.

Numeric audit covered 4,592 conditioned grid scores and 560 paired integer GLRT timing cells on each target. The maximum error was **9.03 × 10⁻¹¹** for screened conditioned scores, **7.80 × 10⁻¹⁴** for fractional margins, **3.01 × 10⁻¹³ sample** for fractional interpolation and **1.16 × 10⁻¹⁰ Hz** for acquired CFO. The ARM outputs passed tolerance comparison and differed at the byte level from x86. The static binaries and original references are packaged for offline reproduction.

| Recording | Candidates | Fine, conditioned and held-pilot CPU ms per candidate | Integer and fractional GLRT CPU ms per candidate | Total CPU ms per candidate |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237 | 32 | 7.79 | 1.65 | 9.64 |
| DS29-0082 | 64 | 7.51 | 1.42 | 9.09 |
| DS29-0519 | 16 | 8.39 | 1.32 | 9.97 |

Native timing used CPU 17 on the Intel Core Ultra 9 285K. Peak native image RSS was 8,656 KiB. The native driver allocated 5,858,144 bytes for the reusable verifier and 2,026,656 bytes for stereo CI16 and both templates. Linked text sizes including the static runtime were 933,791 bytes on x86, 530,108 bytes on Cortex-A9 and 676,957 bytes on AArch64. ARM QEMU timings establish completed runs only. Physical ARM speed remains unmeasured. [Stage figure](portable-verifier-stage.pdf) · [Timing CSV](stage.csv)

## Reproduce the Cortex-A9 check

Run from this report directory after checking the archived members against `manifest.json`. The score output is a fixed little-endian binary record per ranked candidate.

```sh
scratch=$(mktemp -d)
gzip -dc target/cortex-a9/portable-verifier.gz > "$scratch/portable-verifier"
gzip -dc DS26-0237/capture.bin.gz > "$scratch/capture.bin"
chmod 700 "$scratch/portable-verifier"
qemu-arm -cpu cortex-a9 "$scratch/portable-verifier" --self-test
qemu-arm -cpu cortex-a9 "$scratch/portable-verifier" "$scratch/capture.bin" \
  > "$scratch/scores.bin" 2> "$scratch/resources.json"
cmp "$scratch/scores.bin" <(gzip -dc DS26-0237/cortex-a9-scores.bin.gz)
```

The input starts with `LEOVRF01`, a little-endian `uint32` visit count and two 13,333-sample templates as binary64 IQ pairs. Each visit has two `uint32` fields for the visit number and group count, followed by 1,600,000 bytes of interleaved stereo CI16. A group supplies its lane and seed count as `uint32`, then its center and residual bounds as three binary64 values. Each seed supplies its epoch and bin count as `uint32`, then the absolute and residual starting CFO as binary64. The output consists of contiguous 896-byte `PortableVerifierResult` records in per-group rank order. The public header defines each field and flag.
