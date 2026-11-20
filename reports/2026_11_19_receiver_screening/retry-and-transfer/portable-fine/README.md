# Portable original fine CFO scoring

The standalone C scorer reproduced the installed original receiver’s winner and runner-up for all **312 captured fine CFO calls** on x86-64, Cortex-A9 QEMU and AArch64 QEMU. It evaluated **97,272 frequency scores per target** from 16 authenticated stereo visits across four recordings. The maximum absolute score difference from the independent PocketFFT reference was **5.73 × 10⁻¹⁵**. Interpolated residual CFO changed by at most **1.16 × 10⁻¹⁰ Hz**. [Evidence manifest](manifest.json) · [Protocol](PROTOCOL.md)

The C entry takes a 200,000-sample complex window, the original pilot frame template, an integer epoch and the absolute first CFO. It folds the even pilot symbols, rotates the requested first CFO to zero, computes the prefix of the 20,000-point binary64 transform and averages the per-frame normalized magnitudes. A second entry ranks the residual grid and interpolates the peak. The C runtime uses the standard C and math libraries. The integrated host detector still uses the existing Python producer and exact pruned fallback for unsupported or numerically sensitive score grids.

AArch64 produced bitwise-identical output to native x86. The Cortex-A9 score difference from x86 was at most 2.78 × 10⁻¹⁷. The captured suite covered both pilot edges, 161- and 321-bin grids, 14 and 15 complete frames, and two winning scores on the lower fine-grid edge. Exact ties, near ties, a flat peak, asymmetric interpolation and the upper Nyquist boundary also passed explicit numeric sentinels. All captured score grids passed the C peak guard.

## Native host timing

| Recording | Portable fine scorer, mean CPU ms per call | Installed detector, median CPU ms per visit | Exact pruned detector, median CPU ms per visit | Portable detector, median CPU ms per visit |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237 | 3.51 | 794 | 617 | 652 |
| DS29-0082 | 3.43 | 1,230 | 1,021 | 1,044 |
| DS29-0174 | 3.54 | 794 | 657 | 647 |
| DS29-0519 | 3.65 | 749 | 605 | 771 |

These CPU measurements used host core 12 on an Intel Core Ultra 9 285K. The complete detector comparison used three rotated-order repeats per visit and preserved candidate order, integer epochs, gate decisions and all other discrete fields. The largest continuous CFO change anywhere in the normal detector was 2.33 × 10⁻¹⁰ Hz. At DS29-0519 visit 153, the existing conditioned acquisition guard reran one eight-grid acquisition with direct conditioned scores when two score-equivalent candidates became distinguishable by their binary64 CFO. The final packet remained within its numeric bounds. [Stage figure](portable-fine-stage.pdf) · [Timing CSV](stage.csv) · [Tie diagnostic](conditioned-tie-diagnostic.json)

The C scorer owns 1,176,344 bytes of reusable workspace, including roots, working arrays, one folded frame, base rotation and the selected FFT bins. The standalone evidence driver uses another 5,013,328 bytes for original stereo CI16, one converted physical lane and the template. Static executable sizes were 851,464 bytes for x86-64, 4,501,636 bytes for Cortex-A9 and 707,456 bytes for AArch64. Read-only host inventory identified an attached timestamp-capable PlutoSDR+. The run used QEMU for both ARM targets because an authorized board execution route was unavailable. Physical ARM throughput remains unmeasured. [Executable layout and audit seals](supplement.json)

## Reproduce a target replay

From this report directory, unpack the checked Cortex-A9 ELF and one authenticated input into local scratch. The corresponding reference lock identifies each original CI16 digest and every PocketFFT score vector. The manifest has SHA-256 entries for every compressed artifact.

```sh
scratch=$(mktemp -d)
gzip -dc target/cortex-a9.gz > "$scratch/portable-fine"
gzip -dc DS29-0174/captured.iq.gz > "$scratch/captured.iq"
chmod 700 "$scratch/portable-fine"
qemu-arm -cpu cortex-a9 "$scratch/portable-fine" --self-test
qemu-arm -cpu cortex-a9 "$scratch/portable-fine" "$scratch/captured.iq" \
  > "$scratch/scores.bin" 2> "$scratch/resources.json"
cmp "$scratch/scores.bin" <(gzip -dc DS29-0174/cortex-a9-scores.bin.gz)
```
