# Archive-to-detections overhead after the frozen receiver

The existing compressed-buffer path with receiver `107909cc` leaves about **2% of acquisition CPU** in the caller outside verified I/Q and native detection on the two measured prefixes. The complete DS30-0374 detection handoff takes about **55 ms of CPU** including asset validation, manifest inventory, saved JSON read and decode, digest revalidation, and new immutable seals. Dispatch, context batching, and duplicate metadata or detection reads cannot close the remaining publication budget. [Acquisition traces](receiver-ingress-results.json) · [Complete handoff receipt](receiver-boundary-results.json)

| Measured prefix, 40 scheduled visits each | DS30-0016 lower | DS30-0374 upper |
| --- | ---: | ---: |
| Complete acquisition CPU, compressed buffer (ms) | 412.18 | 347.84 |
| Verified I/Q reader CPU (ms) | 147.59 | 146.60 |
| Native factor calls CPU (ms) | 256.61 | 194.26 |
| Everything else inside acquisition (ms) | **7.98** | **6.98** |
| Python receiver adapter above native calls, within that remainder (ms) | 3.03 | 2.23 |
| Receiver opening including pilot read, within that remainder (ms) | 1.58 | 1.57 |

The receiver opens one context for the recording and reuses its asset, filters, FFT plans and native buffers across both physical lanes and every segment. Combining two native calls into one dispatch could save only part of the measured adapter time. The remaining adapter work includes normalization of native factor fields, per-lane continuation and physical probe assembly. The acquisition caller parses each visit's retune receipt once and validates all visits and sample clocks. [Released caller](../../../tools/algo08_scan.py) · [Receiver adapter](../../../tools/pipeline_eval/qualification/blind_compact_run.py)

Inventory creation parses each segment manifest, then constructs a segment source that reads its header again to verify the digest and configuration. Acquisition opens the verified segment source for the payload. Inventory uses `verify_windows=False`, so these repeated reads touch headers only. Each compressed member is read once during acquisition. The compressed, aggregate decoded and per-window digests bind different byte scopes. The decoded bytes flow directly into the NumPy view without an extra NumPy copy. [Inventory and segment reader](../../../src/leo/storage/fast_scan.py) · [Verified short-window reader](../../../src/leo/storage/short_window.py)

## Complete saved detection handoff

The saved DS30-0374 publication contains **4,220,049 detection bytes** with **9,288 ordered lane rows** and 14 segment headers for 6,770 scheduled visits. Seven timed repetitions read the pinned assets, those headers, and the saved detection document. Each repetition checked the input manifest and session, pinned receiver identity, canonical output digest from the terminal result, and the analysis digest over the ordered probes. Republished bytes in an isolated temporary file matched the saved artifact exactly. This comparison used saved metadata and detection results without replaying the I/Q or solver.

| Operation | Median process CPU (ms) |
| --- | ---: |
| Validate the four acquisition assets | 0.39 |
| All 14 header bindings | 3.30 |
| Read saved detection bytes | 0.54 |
| Decode saved JSON | 16.18 |
| Recheck the probe digest | 15.72 |
| Serialize and atomically seal a new copy | 18.93 |
| Publish the immutable inventory | 0.13 |

The cold caller writes the detection artifact once, then reads and decodes it for the solver. Keeping its new in-memory document would save at most the measured **16.72 ms** of read and decode while retaining the probe check, immutable write, and verification on cache reuse. Even eliminating every measured handoff step would save about 55 ms. Theoretical removal of the entire 6.98 ms remainder from each equivalent 40-visit upper-edge slice projects about 1.18 s across the 6,770 visits, deliberately scaling one-time setup as if it recurred. This is an extrapolation from the saved prefix. It is about 1.3% of the measured 93.4 s candidate CPU, including the full handoff budget. [Matched publication](measurements/DS30-0374.json)

The measured bottlenecks at this boundary remain one native detection per physical lane and verified decompression and hashing. The existing compressed single-allocation read already removes the measured duplicate input copies. No further caller change was made.

## Reproduce the metadata and detection measurements

Use the candidate's `detections.json` and `terminal.json` from the saved physical pair and the capture path in its receipt. Run from the research checkout root as the read-enabled account, with the normal shared lock.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_pair="$algo08_work/integration02/physical/DS30-0374"
algo08_outputs="$algo08_pair/candidate/fast-scan-automatic-work"
algo08_recording=$(jq -r '.recording' "$algo08_pair/pair.json")
flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 timeout 80s \
  sudo -n -u leo -- env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=.:src PYTHONDONTWRITEBYTECODE=1 /opt/leo-algo08/current/venv/bin/python \
  reports/ALGO08/single-core-2x/receiver_boundary.py "$algo08_recording" \
  "$algo08_outputs/algo08-v2-c10cfc6a4fff22a8bbf32b6398eaff10/detections.json" \
  "$algo08_outputs/algo08-v2-324d28dd179e7d1b200c6239076d8238/terminal.json" \
  "$algo08_work/integration02/receiver.so" /opt/leo-algo08/current/assets \
  107909cc17e994950f7ffb2dce215114959565d5874122d958a6480132c242a5
```
