# Coarse-authority 30-MS/s tracking qualification

**Date:** 15 September 2026  
**Radio:** `1040005e0b100007100010000bf33a5d4d` (`192.168.1.20`)  
**Image:** `glrt-iq-tracking-r30000000-v1`  
**Result:** implementation and bounded operation pass; ten-second physical tracking does not yet pass

## Result

Retained 2.5-MS/s ARM observations can now extend the causal scheduling
horizon of existing 30-MS/s FPGA pilot jobs. The implementation preserves a
separate native-result history, retains every authority update before use, and
does not rewrite work already submitted to the FPGA. Synthetic positive and
negative controls pass, as do 527 live/controller tests.

Four physical runs exercised the new path. Two acquired the signal and produced
five FPGA episodes. The strongest episode contains **1,158 consecutive FPGA
results, or 1.544 seconds at the 750-Hz pilot cadence**. Its concurrent ARM
observer supports 124 of 130 measurements, while 416 of 1,158 wider native
diagnostics pass their unchanged gate. This is a large improvement over the
previous 74-result/98.7-ms physical maximum, but it remains well short of the
7,500-result/10-second target. The two runs made after the final wall-deadline
fix contain no qualifying handoff, so they cannot validate that fix against a
physical signal.

![Scheduled episode lengths and handoff times](2026_09_15_radio20_30ms_authority_tracking/tracking_outcomes.png)

## Rates and limits

| Component | Rate | Bound or role |
| --- | ---: | --- |
| FPGA receive and scheduled-pilot input | 30 MS/s | 39,600 native samples per 1.32-ms pilot |
| FPGA scheduled measurements | 750 results/s of signal time | 7,500 results define the ten-second target |
| Exported IQ and ARM acquisition | 2.5 MS/s | Continuous GLI1 stream in original 30-MS/s coordinates |
| ARM coarse authority observer | 2.5 MS/s, one pilot every 9 frames (83.33 measurements/s) | Up to 1,024 measurements and 12 seconds of source span |
| ARM native-result retention | Measured about 96.5 results/s in run-v4 | Drains FPGA heads through sysfs; it is slower than signal time |
| Long controller wall deadline | 120 s | Time to drain already authorized results; it does not enlarge the ten-second source horizon |
| Whole worker | 300 s | Fixed total bound; operator alarm is 325 s |

The measured run-v4 drain rate projects 7,500 results in about 77.7 wall
seconds. The new 120-second controller deadline therefore has useful margin
inside the unchanged 300-second worker bound. This remains a projection until a
physical ten-second episode completes.

## Physical runs

| Run | ARM binary | Exported-IQ time | Searches | Handoffs | Longest episode | Terminal observation |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| v3 | `e579af79…7850cf4` | 17.629 s | 18 | 3 | 655 / 0.873 s | Exposed premature descriptor-horizon exhaustion; final episode reported source loss |
| v4 | `c8a39148…7b78e1d` | 139.218 s | 183 | 2 | 1,158 / 1.544 s | Horizon fix worked; controller reached the old 12-second wall deadline |
| v5 | `480b6c60…cbe174` | 215.135 s | 256 | 0 | none | Clean negative dwell after the 120-second fix |
| v6 | `480b6c60…cbe174` | 216.013 s | 256 | 0 | none | Clean negative dwell after the 120-second fix |

Run-v3 episode lengths are 193, 655 and 65 results. Run-v4 episode lengths are
323 and 1,158 results. Run-v4's final episode ended with a controller deadline,
after all 1,158 configured results had been retained and popped. Its native
journal independently decodes with 416 supported results; the observer records
124 supported measurements out of 130. Runs v5 and v6 completed all 256 bounded
search attempts without creating native work. They are negative signal dwells,
not evidence that an acquired track failed.

All four final GLI1 snapshots pass the capture fault/loss checks. Every operator
record confirms the same serial and image after execution, no enabled IIO
buffer, TX LO powered down, and TX gain at -80 dB. Temporary remote files were
removed. Run-v5's independent epoch/ownership review passes with its empty
native journal. The older review schema deliberately does not classify the
run-v4 deadline as a successful episode; the individual journal and capture
checks are reported without promoting it to acceptance.

## Implementation

Firmware branch `codex/radio20-tracking-qualification` contains:

- `67260ed21`: separate retained coarse authority, immutable submitted jobs,
  reconstructed journal authority, and positive/noise/zero controls;
- `ede05fb9e`: descriptor counts use the newest valid authority horizon,
  including a partial final batch;
- `aa8d4070d`: separates ten seconds of source work from the 120-second ARM
  drain deadline and records both limits accurately.

The final focused suite passes **527 tests**. The current ARM executable SHA-256
is `480b6c60a212af3c5d17a4b365164b4bdf8021df8c229d06155f295a92cbe174`.

## Evidence and acceptance

The four runs were written to NVMe first. All 51 evidence files were then copied
to
`/srv/bulk/leo/glrt-deployment-20260909/radio20-iq-tracking-20260912/authority-track10-30ms-20260914-v1`.
The SSD and RAID SHA-256 manifests match for every file; the 246-MB RAID copy
contains `SHA256SUMS`, and the SSD originals remain in place.

The acceptance gate remains:

1. two repeatable episodes of at least 7,500 results/10 seconds;
2. clean loss and reacquisition;
3. zero active capture, CDC and pacer drops;
4. exact radio and TX-safe restoration.

This campaign establishes the implementation, causal authority chain, zero-loss
capture, clean negative behavior and restoration. It records zero qualifying
ten-second episodes, so acceptance is **not passed**.

The next stable step is to connect this authority profile to the existing
bounded frequency-visit scanner. Recent fixed-frequency yield is too sparse:
all five handoffs clustered in runs v3/v4, followed by 512 unsuccessful searches
over two long dwells. A multi-frequency acquisition pass can select an active
channel before spending the bounded 120-second native drain budget. Once a
same-frequency handoff appears, repeat the unchanged v3 binary until two
ten-second completions and a clean loss/reacquisition are retained. Native
diagnostics should remain separately labeled; their lower support rate is not a
reason to alter the coarse authority or its gates.

The figure and `summary.json` are regenerated by
[`analyze.py`](2026_09_15_radio20_30ms_authority_tracking/analyze.py) from the
hash-verified RAID evidence.
