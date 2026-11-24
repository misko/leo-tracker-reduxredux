# Whole-stereo thinning before native 8 ms carrier history

The frozen two-of-three short stereo mask **reversed North’s held-anchor decision** from history to unfiltered. Its fixed-zero error grew **660 m** against all-visit 8 ms, and fitted error grew **34 m**. The same mask left weak DS30-0016 on the unfiltered route. Its fixed-zero error fell **55 m** and fitted error grew **129 m** against its earlier all-visit 8 ms result. Both cases fixed. North failed the frozen accuracy gate. The masked route ran through two saved publications with original causal inputs and zero waveform calls. [Frozen protocol](whole-stereo-8ms-protocol.md) · [Verified census and publication receipts](measurements/whole-stereo-8ms.json.gz)

## What the mask changes before the fit

The census reproduced both all-visit 8 ms detector digests and held choices exactly. The frozen schedule paid both radios at every eighth originally admitted visit and at the first two of every three remaining slots in each exact RF, channel and pilot-edge stream. It carried every original delivery clock, excluded opportunity and real empty slot forward. A skipped slot had two empty candidate lists before chronology or held-anchor training began. Both branches consumed actual 8 ms signed nonanchor CFO and timing with no tail calls. The original held score still has seven nominal donor slots per held anchor. It gives a skipped slot no vote and has no separate missing-observation correction. [Original whole-stereo schedule](whole-stereo-blocks-protocol.md) · [All-visit 8 ms history](eight-ms-native-live.md)

| Evidence before fitting | North all visits → masked | DS30-0016 all visits → masked |
| --- | ---: | ---: |
| Original issued / admitted visits | 1,200 / 1,200 | 808 / 713 |
| Paid full / short lane calls after masking | 304 / 1,408 | 186 / 832 |
| Omitted short lanes / stereo visits | 688 / 344 | 408 / 204 |
| Observed factors before history | 1,595 → 1,089 | 506 → 351 |
| Held anchors per radio, positive counts | 144 each, 39 / 39 unchanged | 85 each, 43 / 27 unchanged |
| Held log-score gains by radio, nats | +92.630 / +83.174 → +4.191 / −4.270 | −25.287 / −11.749 → −28.189 / −18.856 |
| Chosen route and factors | History → unfiltered, 456 → 1,089 | Unfiltered → unfiltered, 506 → 351 |

On North, the masked history alone would keep **228** of the old 456 selected factors. It drops 136 directly and another 92 on later paid slots. The actual unfiltered decision keeps the 320 still measured from the old selected set and adds **769** other paid measurements. Of 1,089 chosen, 82 are unchanged measured full-anchor factors and 1,007 come from paid short slots. On weak, the actual unfiltered route loses 155 short factors directly. Its diagnostic history would fall from 289 to 178 factors, with 94 direct losses and 17 later on paid slots. Identical held anchor labels and count therefore do not preserve which signed observations reach the solver. The comparison does not estimate counterfactual CFOs on omitted opportunities. [Per-radio coverage and held diagnostics](measurements/whole-stereo-8ms.json.gz)

## Position and RF fit

| Containing offer and recipe | `c = 0` / fitted position error, m | `c = 0` / fitted RF RMS, Hz |
| --- | ---: | ---: |
| North named v3 | 105.690 / 140.779 | 5.406 / 5.167 |
| North all-visit 8 ms, same combined build | 111.954 / 128.086 | 9.133 / 8.921 |
| North masked 8 ms, recomputed held policy | **771.969 / 162.150** | **11.590 / 9.899** |
| North separately reported unfiltered masked 20/12 ms | 819.705 / 110.595 | 8.433 / 7.484 |
| DS30-0016 named v3 | 1,643.669 / 1,661.443 | 109.375 / 109.479 |
| DS30-0016 all-visit 8 ms, earlier saved build | 490.071 / 980.010 | 134.021 / 133.740 |
| DS30-0016 masked 8 ms, recomputed held policy | **434.846 / 1,108.852** | **131.029 / 130.938** |
| DS30-0016 separately reported unfiltered masked 20/12 ms | 1,524.715 / 1,738.538 | 125.685 / 124.610 |

North retained 217 of 342 old owners and acquired 102 new ones per arm. Nineteen shared roles changed and all shared NORADs agreed. Weak retained 79 of 115 owners with no additions or shared NORAD and role changes. Both solves used the original offers and archive cutoffs, accepted the named signed finish, paid no inference fallback, and published all eight verified official PNGs and the complete matched position grids and paths. Both combined options executed. North and weak used 320/48 compact rank profiles and 11/19 portable archive hits. North geometry used 25 regional probes and 137 final grid points. Weak used 25 regional probes and 179 grid points. Weak all-visit 8 ms is the earlier saved solver with the same calibrated method and older preparation options. The separate North 20/12 comparison is a real raw unfiltered publication with the same schedule digest. The weak 20/12 comparison is a saved unfiltered publication with the same mask. [North 20/12 timing and science](/dev/shm/leo-live-stereo-north.BYuWvuyj/pair/result.json) · [Weak 20/12 study](whole-stereo-blocks.md) · [Earlier weak 8 ms saved science](eight-ms-held-fit.md)

## Timed boundary and receiver budget

| Scope | North | DS30-0016 |
| --- | ---: | ---: |
| Mask, unchanged selector and signed staging CPU | 0.056 s | 0.029 s |
| Fresh saved worker through exit, elapsed / CPU | 5.747 / 5.742 s | 4.512 / 4.497 s |
| Saved worker plus charged planner, elapsed / CPU | 5.803 / 5.798 s | 4.541 / 4.526 s |
| Numerical solve CPU | 3.431 s | 2.335 s |
| Original 8 ms short-call CPU pool | 1.857 s | 0.995 s |
| Omitted calls priced at original mean 8 ms cost | 0.610 s | 0.328 s |
| Estimate after charging the measured full planner | 0.553 s | 0.298 s |

All original compressed reads, decoded checks, full anchors, and publication remain charged. The omitted subset has no per-lane native timing. The short-call pool is a hard ceiling on this particular receiver saving at the measured baseline. The omitted mean-price estimates assume representative lane costs. Even granting every North short call for free would leave **0.591 s** of its previous **2.448 s** half-time gap with the rest unchanged. The same-build all-visit North comparison took 10.828 s raw through exit and nested 3.345 numerical CPU s. The masked numerical solve was 86 ms more expensive. Its saved launch/exit clock excludes raw ingestion. Weak’s earlier all-visit 8 ms took 4.516 s from saved input through exit under older preparation. The new saved clock plus planning shows no demonstrated software savings there outside the projected receiver calls. The paired North and weak masked 20/12 receipts measured 14.020 s from raw and 5.113 s from saved respectively. Those timing boundaries belong to their independent builds.

The North scorer initially compared the offered JSON directly with the normalized published region, which includes a default screen centre. The corrected read-only check validated the same terminal and figures. It also recorded the candidate’s actual held route and solver flags instead of fields inherited from the prior full-visit identity. The weak preflight stopped in **0.141 s elapsed / 0.133 s CPU** on an archived input permission before inference. The archive-readable account completed the only weak solve. Its read-only scorer then used the authority document from the same pinned repository commit. The process clock reported 112/40 input blocks on North/weak while waveform entry points were closed. Saved startup and allocation clocks differ across the two launches. North's accuracy result admitted the weak case and ended the omitted-offer branch.

Freeze `b9a779d7e` covers the mask, selector, plan and North worker. `7a04ebeef` corrects published region normalization and pins the follow-up launch separately. Use `whole_stereo_8ms_trial.py plan FRESH_TMPFS_ROOT`, then `launch ROOT north`, `seal ROOT north`, `score ROOT north`, and the admitted follow-up. Run numerical launches under the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread, using the archive-readable account for weak. Twenty-eight focused tests passed. [Planner](whole_stereo_8ms.py) · [Saved worker and independent scoring](whole_stereo_8ms_trial.py) · [Component tests](../../../tests/pipeline_eval/test_whole_stereo_8ms.py)
