# Centering the 12 ms primary

Centering retained **29 of 36** highest-margin installed v3 factors on the weak physical clips versus **27 of 36** with the prefix. On the authenticated dense DS30-0008 prefix, both matched **30 of 43** on short-primary lanes. The dense antenna counts moved from **21/26 and 9/17** to **22/26 and 8/17**. The decline on the second antenna failed the prespecified northern-transfer gate. Neither a northern run nor a full recording followed. [Frozen protocol at `ab559fd34`](centered-primary-protocol.md) · [Per-lane receipt](measurements/centered-primary.json.gz)

| Physical cohort | Short lanes | v3 rank-zero matches, prefix → centered | v3 highest-margin matches, prefix → centered | Unmatched proposals, prefix → centered |
|---|---:|---:|---:|---:|
| Original DS26 clips, five recordings | 36 | 30/36 → 28/36 | 27/36 → 29/36 | 2 → 2 |
| DS30-0008, first 48 scheduled visits | 80 | 31/43 → 33/43 | 30/43 → 30/43 | 2 → 3 |

On weak clips, four highest-margin matches appeared and two disappeared. On dense short lanes, two appeared and two disappeared. A match uses two wrapped pilot samples and 250 Hz of signed CFO, with the original gate and no site information. New proposals lack a match to either installed v3 factor on the same antenna and visit. They can include signals the original detector missed. Across lanes where both short apertures proposed a factor, the median absolute aperture-to-aperture CFO difference was **62.66 Hz** on weak clips and **69.29 Hz** on dense clips. These are small receiver comparisons and contain no position fits or observation-owner labels.

## Native aperture and metadata

The candidate takes the same eight frame origins as the prefix receiver after advancing its original contiguous stereo CI16 pointer by 40,000 samples. Its local frame `f` corresponds to original frame `f+3`. The exact step of 40,000 samples over three frames also lies on the scout's four-sample grid. The native integer and fractional in-frame epoch therefore stay in the same original coordinates. Taking the input shift modulo the approximate integer period of 13,333 samples would create a spurious one-sample offset. The stored 20 ms support and its original start counter remain intact. The position adapter continues to use `valid_start_counter + 10 ms` for observation time. Selecting different I/Q can alter timing, signed CFO and scores. Neither path extrapolates CFO to the metadata timestamp. [Earlier source-epoch audit](short-primary-epoch.md) · [Native wrapper](centered_primary.c)

The relinked control reproduced the original prefix library digest. The centered library has SHA-256 `1c77b3d9ad977d9de871ff786bfac16b03fdb0a67923a721bedd284622bddb17` and the same exported ABI. The installed 20 ms library, schedule and candidate margin selection were shared on all 16 dense anchor calls, and all anchor probes were identical. Probe metadata was identical on every measured lane. On **136** short lanes the centered output matched the original prefix engine on an explicit `[40000,160000)` view byte for byte and survived replacing both wings with saturated samples. A positive plant also returned byte-identical timing, CFO and scores for both antennas with an inaccessible page immediately before the crop and again immediately after it. The experiment uses the ordinary mixed callback with its original shape, stereo order and type assertions. Native disassembly shows a single 320,000-byte pointer adjustment before calling the original scout and independent verifier. It introduces no I/Q copy or second call. [Build and parity checks](centered_primary.py) · [Tests](../../../tests/pipeline_eval/test_centered_primary.py)

## Measured callback cost

| Cohort and original stereo visits | Prefix CPU / elapsed ms, two orders | Centered CPU / elapsed ms, two orders |
|---|---:|---:|
| Weak 18, forced 12 ms primary on each lane | 47.732/47.733, 44.249/44.250 | 46.508/46.509, 44.593/44.594 |
| Dense 48, full anchor on one of eight visits per stream | 145.824/145.835, 137.134/137.138 | 146.961/146.965, 137.524/137.533 |

The dense centered complete callback was **0.78% and 0.28%** above prefix. Dense native-only short CPU was **92.812/87.407 ms** prefix and **94.735/87.929 ms** centered. Setup was measured outside the callback. The first arm in each measurement process paid 757 ms or 464 ms of cold setup, while subsequent observed setup ranged from 3 to 14 ms. These clocks include the research callback and native calls, and exclude signed fixture ingestion, solver and publication. They do not determine a whole-recording speedup. The initial dense cache-only attempt returned `EAGAIN`. The later attempt staged the same first member with `RWF_NOWAIT`, with no blocking waveform reads, and checked the original manifest and index, **77,442,779** compressed bytes, all original windows and **102,400,000** decoded bytes before using its first 48 visits. The signed digest chain remains in the receipt. [Cache-only stage](centered_primary_cached.py)

## Independent signed plants

Both short apertures matched every full-support, early-support and late-support plant across both pilot edges and CFO signs, **12 of 12** each. The centered maximum error versus planted phase and CFO was **0.331 samples and 8.49 Hz**, compared with **0.427 samples and 10.45 Hz** for prefix. All three receivers rejected all four noise lanes. All three accepted all four rolled-pilot cases at a pilot phase shifted by about **748 samples** from the unrolled plant. The waveform supports and relative noise were fixed before scoring. This control checks phase transport and exposes a common shifted-candidate behavior of the existing gate.

## Reproduction

From this worktree, the original capture account must be able to read the signed archive and the first member must be available from the page cache. The runner can finish the weak and planted comparisons if the dense cache-only path declines. The low-priority shared Gauss slot is used for build and receiver measurement. Eleven focused and adjacent tests passed.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
weak=/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src" \
  "$release/venv/bin/python" -m reports.ALGO08.v3.centered_primary "$weak" /tmp/centered-primary-reproduction
```
