# Complementary full-anchor acquisition

The anchor race retained 17 of 48 original capture-era gate-positive candidates, with 1,038 ms median host CPU per complete dual-receiver call. It recovered one of four held targets that wide stock had missed and dropped both held targets that wide stock had detected. The same-support pooled mean made the same held decisions and used 1,003 ms median CPU. The earlier wide stock detector matched 42 of 48 original gated candidates at 25.9 ms median CPU on this panel. [Detector chart](anchor-race.pdf) · [Timing CSV](timing.csv) · [Qualification data](qualification.json)

## Saved IQ comparison

The locked panel scheduled 17 dual-receiver windows across four recordings and kept an original invalid capture outside the detector timing denominator. The 16 processed windows each had two rotating warm measurements. Six visits represented four independently selected prior wide misses and two prior wide matches. The installed capture release reproduced all admitted archived probe rows byte for byte. The six held wide outputs also matched their own locked baseline. [Protocol](PROTOCOL.md) · [Source and visit lock](source-lock.json)

| Detector | Original positives matched | Additional candidates | Held misses recovered | Held matches kept | Host CPU p50 | Host wall p50 / p95 |
|---|---:|---:|---:|---:|---:|---:|
| Installed capture | 48/48 | 0 | 4/4 | 2/2 | 2,373 ms | 2,438 / 4,856 ms |
| Pooled mean | 14/48 | 3 | 1/4 | 0/2 | 1,003 ms | 1,057 / 2,596 ms |
| Anchor race | 17/48 | 3 | 1/4 | 0/2 | 1,038 ms | 1,070 / 2,210 ms |
| Rotated sham | 0/48 | 0 | 0/4 | 0/2 | 1,044 ms | 1,067 / 1,468 ms |
| Wide stock | 42/48 | 26 | 0/4 | 2/2 | 25.9 ms | 26.0 / 31.1 ms |

Original gate-positive records match within two fractional samples and 1 kHz after allowing established aliases. The held physical targets use unfolded CFO. Additional positives are candidates the original did not emit. Their truth is unknown. Empty and seeded Gaussian input produced zero gated candidates in both edges and in all five methods. Anchor race, pooled mean, wide stock and installed capture each gated the planted weak +48 kHz and strong ±720 kHz targets on both receivers across both edges, 12/12 planted lane targets. The rotated sham also found two strong planted lane targets by chance. [Individual waveform outcomes](qualification.json)

## Acquisition and cost

Two native correlation calls score disjoint landmark sets. Each uses a different four complete original anchor waveforms on two distinct frames, while visiting every original epoch/CFO cell. The first branch ranks by the smaller panel score. The second ranks by the larger score and fills the unused portion of the fixed 64-basin shortlist. The original epoch/CFO suppression carries across both branches. The mean control pools the same two surfaces. The sham rotates the same completed nominations around the frame and keeps the primary rescore cell budget. Different normal detector retry decisions can change the total per-call work.

The original native kernel scored all anchor and frame contributions at all CFOs in the merged ±6-epoch neighborhoods. All 753,102 comparable rescored race cells were bitwise equal to the installed original on releases where its dense grid was exposed. The race retained every original first-pass key inside an exact scored neighborhood, 28 of 256 overall. Fifteen kept their exact ordered rank, and four kept rank one. The same-support mean retained 25 keys overall and 9 of 96 on the six held visits, versus five on those visits for the race. The rotated sham retained 11 keys overall. The earlier two-frame/four-anchor experiment retained 19 of 160 keys on the reused panel, where the new race reached 23 of 160 with twice the shortlist size. [Prior thinning comparison](../../acquisition-support/thinned-capture/README.md)

The race evaluated 978,852 exact rescore cells across 70 acquisitions including retries, 5.0% of the original grid cell inventory. On each paired visit, median race CPU was 43.0% of installed capture CPU. Proposal scoring, nomination and exact rescoring took 161, 62 and 202 ms median CPU per dual visit. Measured CPU after subtracting the inclusive coarse and final peak selection clocks still had a 608 ms median. All 32 measured race wall times exceeded 20 ms. The selected full waveform runner was the installed x86 release on host CPUs 12 and 13. The peak process RSS ranged from 251 to 1,249 MiB and includes the original detector, wide control, all candidates and authenticated archive data in one paired harness. This experiment does not establish a standalone candidate memory bound or device runtime.

## Reproduce

The stage ends at published candidate gates. There are no whole-recording position predictions for this variant. The plot, timing table and candidate accounting can be reproduced without the waveform archive from the sealed per-recording receipts.

```sh
python -m tools.pipeline_eval.qualification.anchor_race_results --out /path/to/local/output
```

For waveform replay, use `tools.pipeline_eval.qualification.anchor_race_eval <recording>` with its attested producer `src` first on `PYTHONPATH`, the repository second, and the installed `/opt/leo-fast-auto/20261010-r1/venv/bin/python`. The evaluator requires the existing source lock. Its opt-in scorer calls the installed native anchor kernel directly. [Installed capture provenance](../../detector-origins/lineage/README.md) · [Evidence seal](evidence-lock.json)
