# Complete physical DS30-0016 on the compatible visit-frame archive

On the same new standard-format archive, the optional index cut total elapsed time from **7.653 to 6.890 s** and authenticated acquisition from **3.048 to 2.352 s**. Both children completed the same signed 20/8 ms receiver, history-risk solver, full position grid and eight Cairo PNGs. The indexed path authenticated every encoded byte and decoded only the original detector apertures. [Frozen protocol](visit-frame-raw-0016-protocol.md) · [Paired receipt](measurements/visit-frame-raw-0016.json.gz)

| Raw scope | Ordinary | Visit-frame index |
| --- | ---: | ---: |
| Through-exit elapsed | 7.652804 s | 6.890240 s |
| Through-exit CPU | 7.635254 s | 6.864916 s |
| Authenticated acquisition elapsed | 3.048334 s | 2.352135 s |
| Native acquisition CPU | 3.048110 s | 2.351973 s |
| Held selection elapsed | 0.048275 s | 0.048679 s |
| Decision and publication elapsed | 4.007955 s | 3.941584 s |

Elapsed fell **0.763 s (10.0%)** in this one matched pair. Most of the gap is inside acquisition, with 0.066 s difference elsewhere in the decision and publication stage. The ordinary reader submitted and used 11 member-prefetch buffers over 834.8 MB. The index uses the committed member directly and submitted none. This is a comparison of the two complete reading paths on the same encoding. Both captured 808 issued and 713 admitted visits, with 95 invalid opportunities and 506 final factors. The indexed path verified all 13 compressed seals covering **991,704,602 bytes**. It passed 93 full visits and 620 prefixes to the native detector, feeding **416,654,057 encoded bytes** to Zstandard and yielding **545,600,000 decoded bytes**. The ordinary stream independently decoded and checked every window, totaling **1,292,800,000 decoded bytes**. [Reader accounting and exact scanner port](visit_frame_input.py)

The original recording and all original waveform archive reads had already been staged for the writer. Neither analysis read backing radio or TLE files. All 242,720 new source pages and 20,102 original causal pages remained resident. Both new raw children used CPU 2, nice 15 and best-effort I/O priority 7 and each recorded zero input blocks and major faults. The ordinary child ran first. Candidate-specific custody setup took **1.478 ms elapsed** inside the indexed child's through-exit clock. Shared outer admission took 13.412 ms, outside both child clocks. Its early attempt stopped at the cache check before either raw child because the controller omitted the reader's expected member-count field. The corrected single paid pair ran at `a1776882d`. [Admission and process logs](measurements/visit-frame-raw-0016.json.gz)

## Recording identity and scientific invariants

The writer produced a new ordinary inventory `sha256:c542d45d…c13549f`, raw authority `sha256:af1c330c…780582b` and session `fast-c542d45d28d2ed8894a5b67695154b63`. Its two new manifests retain the original 512/296 ordering, fault lifecycle, exact index and complete decoded member commitments. Its separate ordinary full readback authenticated all **808** original windows, and the optional reader independently verified all **808** prefixes. Both current raw arms use their genuine new acquisition `sha256:a2c4675b…9779f20` and terminal `sha256:3cb4e67b…bcc3b820`. They reproduced the same two calibration endpoints and RF RMS, 115 ordered owners per arm, path and all 179 grid evaluations. Every current pair PNG matched in encoded bytes and decoded pixels, and each grid and path binds its verified position PNG. [Full writer evidence](measurements/visit-frame-raw-0016.json.gz)

The older original-encoding Cairo process used different authenticated workflow IDs. After excluding the explicitly changed source session, input, analysis and raw digests and the derived provenance run ID, its native document matches the new full native document exactly, including all ordered RF factors, delivery clocks and rejected visits. Each engine derives its observation IDs from its own signed `session_id:receiver_id:valid_start_counter`. A unique bijection reconstructed from the signed probes shows all 115 physically identical assignments and roles in order in each arm. The original and new horizontal errors are **0.490 / 0.980 km**, and terminal RF RMS values are **134.021 / 133.740 Hz**, for fixed zero and fitted (c\). The complete path and grid scores are identical across the change in archive identity. [Score implementation](visit_frame_raw_score.py)

The historical and new Cairo PNGs differ in both encoded bytes and pixels. The released scanner passes the recording name into the renderer. Actual pixel differences are confined to the recording-title bands, at y 36–67 for orbit sheets, 28–46 for residual sheets, 71–91 for track RMS, and 21–40 for position. All pixels outside these bands agree exactly. The initial literal score remains available and records the historical observation-hash and image mismatches. It is distinct from the exact fresh-pair and provenance-aware historical checks. [Initial literal score](measurements/visit-frame-raw-0016-literal.json.gz) · [Per-figure pixel boxes](measurements/visit-frame-raw-0016.json.gz)

## Materialization and historical timing

| Earlier or separate timing scope | Elapsed |
| --- | ---: |
| Historical installed ALGO08v3 on the original format | 10.745 s |
| Historical exact 20/8 history-risk+Cairo on the original format | 7.677 s |
| Historical prepared strict private derivative with setup | 6.542 s |
| New compatible writer, including visit tables and custody | 2.046 s |
| Independent complete ordinary readback | 2.577 s |
| Independent all-prefix readback | 1.622 s |
| Original archive hydration into owned samples | 2.167 s |
| All preceding materialization and readback stages | 8.412 s |

The new index prepared run is **1.559×** against the historical installed denominator and **1.114×** against the same-encoding ordinary child. The new ordinary child is **1.404×** against that historical installed denominator, but it includes a different receiver, solver and renderer configuration from installed v3. Charging all measured materialization and independent reconstruction serially makes the first indexed analysis **15.303 s**, before common admission. The new encoded waveform is just 29,995 bytes smaller than the original. The complete new archive with visit tables and custody is 994.1 MB. There is one ordinary payload copy, and the timed acquisition still reads that full encoded payload. These one-run figures do not establish backing-device or repeated-use performance. [Historical scopes](strict-cairo-0016.md) · [Completed original-input Cairo](history-risk-0016-cairo.md)

The detached custody and writer receipt pins are `afb5a48420d0c1ab9d021e61aab59e3898298b27b0a998fd193dd823ef2383a3` and `bf246173e0a702ac89cc1a589e6db57388fe65a60f436b77c747ad05b33e3ebc`. Use `visit_frame_raw_0016.py launch FRESH_TMPFS_ROOT` inside the shared Gauss slot with the release interpreter and original staged inputs. Run `score FRESH_TMPFS_ROOT` separately with the repository and `src` on `PYTHONPATH`. The new CLI enables the reader with `--visit-frame-custody` and `--visit-frame-custody-sha256`. The trial shares the member authentication implementation with the earlier one-member study. Eleven focused and adjacent tests passed. [CLI](exact_named_raw.py) · [Runner](visit_frame_raw_0016.py) · [Shared reader](visit_frame_reader.py) · [Tests](../../../tests/pipeline_eval/test_visit_frame_input.py)
