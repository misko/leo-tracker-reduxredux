# Conditional antenna processing in the portable receiver

The portable saved-IQ receiver runs the stock detector by default. Select `--detector second-on-miss` to run the other antenna only when the primary antenna has no candidate that passes the fractional-margin gate. The primary alternates independently at each exact recorded RF center. The application retains both physical probe envelopes and feeds the resulting data into the same two-arm compact phase-release solver. [Download the receiver](portable-receiver-conditional.tar.gz) · [Usage and input format](USAGE.md) · [External checksum](SHA256SUMS)

```sh
python -IB portable-receiver/receive.py capture-input.json \
  --out conditional-result --detector second-on-miss
```

## Deployment verification

The application ran from a relocated install with the source checkout, stock build, and acquisition producer masked. It authenticated all **20,318 saved visits** on two upper-edge and one lower-edge captures, including every segment boundary and all 1,906 original invalid visits. On each of the 18,412 valid visits, the measured primary and partner decision and both native probe rows exactly matched an independent projection of previously measured dual-stock packets. The two upper-edge recordings reproduced the independent direct conditional trial's entire native documents byte-for-byte. The lower-edge replay matched its independently projected native SHA and same-input compact fit. On all three, both arm coordinates, RF RMS, numerical scores, and decisions matched after excluding stage timings. [Parity and segment boundaries](parity.json) · [Sealed outputs and receipts](result-lock.json)

| Complete saved recording | Raw replay wall / CPU (s) | Position wall / CPU (s) | Service wall (s) | Position process peak RSS (MiB) | Native receiver calls omitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0014 · upper | 119.35 / 113.83 | 38.72 / 37.21 | 163.32 | 278.5 | 1,990 / 13,544 |
| DS29-0082 · upper | 95.97 / 91.99 | 29.91 / 27.84 | 131.40 | 319.8 | 1,037 / 9,736 |
| DS29-0491 · lower | 109.84 / 107.30 | 34.31 / 34.00 | 148.96 | 296.1 | 2,480 / 13,544 |

All three services reached the physical 512 MiB cgroup boundary with zero swap and completed on the first raw-processing CPU listed in their request. Native per-visit P95 host elapsed was 17.49–18.09 ms. Raw replay wall includes local decoder work and authenticated compressed capture reads. Stock's two-worker scheduling and the historical staggered package's short detector test have different timing boundaries. The omitted calls are measured work reductions against processing both antennas, and the elapsed values apply to these saved-IQ host runs. [Resource chart](resources.pdf) · [Clock and resource data](resources.csv)

## Package size

| Portable release | Application files | Python files | Shared objects | Installed bytes | Download bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Historical stock | 201 | 194 | 3 | 5,109,596 | 1,604,335 |
| Conditional | 203 | 196 | 3 | 5,117,945 | 1,607,091 |
| Historical staggered | 214 | 205 | 5 | 10,032,997 | 3,619,900 |

The stock detector and both position libraries are byte-identical to the original release. The extra 8,349 installed bytes comprise two Python files and the optional branch in two existing files. Python requirements and system-library dependencies are unchanged. The protected archive reader account was used for this qualification. A service preflight exposed a package manifest permission error before any IQ was read. The published artifact corrects the file mode and preserves those first logs separately. [Per-file manifest](release-files.json) · [Package lock](package-lock.json) · [Source lock](source-lock.json) · [Lower-edge source lock](lower-source-lock.json)
