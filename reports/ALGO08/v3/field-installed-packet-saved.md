# Charted successor on the installed full-20-ms detector packets

Both crossovers passed the fixed geographic and publication gates using the exact installed detector packets. DS30-0220 reproduced both installed numerical fixes and spent 44.767 seconds on saved publication. The difference from its 13.976-second mixed-packet publication came mainly from an ordinary solver fallback. DS30-0086 spent 16.050 seconds on saved publication and reproduced both owner maps, with horizontal error increasing by less than 50 m per arm. Neither crossover establishes a 2× raw speedup. [Frozen protocol](field-installed-packet-saved-protocol.md), [0220 score](measurements/field-installed-packet-saved-0220.json), [0086 score](measurements/field-installed-packet-saved-0086.json), [field-stage budget](installed-receiver-field-budget.md).

## DS30-0220

The saved child took 45.626 s wall and 44.375 CPU s through process exit, including a 0.500 s wall / 0.301 CPU s guarded preamble. The charted publication itself used 44.767 s wall / 43.744 CPU s. The original native packet was republished byte-identically, and the native and terminal files appeared at 2.140 and 43.491 seconds from child launch. The independent offline readback took 1.920 s wall / 1.710 CPU s in a separate process. The child used CPU2, nice 15 and I/O priority 7. The 50 fixed causal snapshots came from the existing RAM stage and matched the dated archive pin. No waveform or backing archive was read. Process-wide accounting recorded 257,640 input blocks and 624 major faults. The historical installed raw process was 116.914 s and its verified raw-to-publication stopwatch was 117.961 s.

Both publications completed. Horizontal errors were exactly 318.065 m at `c = 0` and 368.850 m at fitted `c`. RF RMS was exactly 138.100812 and 137.798174 Hz, respectively. The terminal and both owner maps matched exactly, each with 2,817 owners. The candidate’s ordered rows were independently checked against its published maps. The archived installed receipt predates that row evidence, so original row order and roles are unverified. The 179-point numerical grid and native path matched. All eight charted PNGs passed actual decoding and manifest checks. Each encoded and RGBA digest differed from the named renderer’s PNG. A renderer-registration comparison is outside this scientific and evidence gate.

### Paid solver branches

| Existing stopwatch, wall / CPU s | Exact installed-packet saved child | Historical mixed packet |
| --- | ---: | ---: |
| Reported publication envelope | 44.767 / 43.744 | 13.976 / 13.137 |
| Analyze, inside publication | 43.144 / 42.664 | 12.241 / 12.034 |
| Solve, inside analyze | 41.292 / 40.896 | 10.521 / 10.455 |
| History preparation, inside solve | 2.347 / 2.320 | 2.172 / 2.140 |
| History inference, inside solve | 38.765 / 38.419 | 8.205 / 8.195 |
| Lean proposal through gates and repair, inside inference | 5.539 / 5.431 | 5.845 / 5.837 |
| Ordinary fallback, inside inference | 33.204 / 32.966 | None |
| Grid, inside inference/evidence | 2.851 / 2.847 | 2.075 / 2.073 |
| Render, inside publication | 1.630 / 1.546 | 1.405 / 1.358 |

The publication wrappers differ at the outer boundary. The inner instrumentation records the same named methods in the frozen charted build. Their initial cold costs were 2.797 and 2.789 wall seconds. Both paid for two-centre scouts and three distinct finalists, then failed the initial pair test. On the full-20-ms packet the lean repair rejected three tracks and 124 of 2,445 curved positions, with zero predictive rejections and zero refits before hitting `repair_rejection_cap`. The ordinary fallback repeated ranking, 2.719 s wall / 2.715 CPU s across eight nodes. The installed constrained route recorded two calls and 11.192 CPU s, including 20 phase fits totaling 10.978 CPU s. Grid work is already included in the fallback. Other fallback work has no disjoint breakdown.

The mixed packet dropped one track and 23 of 1,809 curved positions, paid a successful refit at 0.237 s wall / 0.237 CPU s, then spent 0.052 s on signed-history qualification with no accepted correction and 2.257 s wall / 2.254 CPU s on ordinary evidence. The published refit moved the mixed errors from 1.128/1.065 km to 1.412/1.371 km after retrospective scoring. The full-packet lean errors were 3.784/3.785 km. Its fallback restored the installed endpoints at 0.318/0.369 km and the original RF values. The outer inference had 22 ms of unassigned CPU on the exact-packet path after subtracting the pre-evidence and fallback callbacks. The timing budget charges each broader stage once.

#### Constrained-rescue arm order

The charted fallback already used the prepared screens, whitening and profile arithmetic offered by `named_constrained_research.py --constrained prepared`. Its witness pins `exact_named_route.py`, `stock_exact_gate_0402.py` and `exact_noise_gate_0402.py`. The pinned charted declarations match all six definitions in the portable prepared implementation. The measured calls include 70,470 screens, 29,232 whitening requests and 41,238 profiles. The charted binding retained the original two-arm order and recorded both complete constrained trials. [Charted witness and counters](measurements/field-installed-packet-saved-0220.json) · [Portable prepared implementation](prepared_constrained_checks.py).

Neither constrained trial supplied the published endpoint. In both arms, the accepted path records five `accepted_optimizer_iterates` rounds with 7, 4, 2, 1 and 1 points. The pinned `algo08_position.selected_packet` passes the selected policy arms' histories unchanged to `recorded_fit_path`. The installed `feasible_fit` returns a round endpoint without optimizer history, so any selected constrained arm would appear as `phase_round_endpoint` throughout. The exact numerical path also matches the installed original. The two constrained alternatives could have failed mandatory gates or lost adoption after qualifying. The publication contains only the selected path. The detailed trial records, per-arm minimum slacks, compatibility flags, corrected losses and individual timers were not written to the sealed outputs.

Both explicit arm orders can skip five phase fits per trial only when the completed first arm reports a failed conditional or predictive track. The existing guard still evaluates the other arm on a passing or unresolved record, even if the completed proposal later loses on phase, region or loss. The available evidence establishes no skippable trial. For either order, zero, five or ten skipped phase fits are consistent with the archive. It records 522 total visits, 10.978 CPU s inside the fits and 11.192 CPU s for both constrained calls including 0.214 CPU s outside the fit timers. Those total timers bound the corresponding measured scopes. Visits and CPU per arm are unresolved. Work after the constrained calls lacks a separate timer. The archive supports no ordering preference or projected wall saving for 0220. [Exact first-arm rule](constrained_pair_veto.py).

DS30-0402 measured a valid speedup after both arms independently failed track checks, with 335 fixed-zero visits versus 58 fitted visits. DS30-0155 verified the portable launcher with no offered constrained fit. DS23-0047 is a concrete example of a constrained pair that passed both arms but lost on adoption score. DS23-0068 had both first-arm vetoes available and supplies historical visit counts. These are separate source and branch checks. No new run or candidate change was made for 0220. [Measured and archived transfers](paired-veto-0402.md) · [Portable launcher transfer](constrained-research-cli.md).

### Same-case budget

The half-time target is 58.980 s. Subtracting the actual 44.767-second saved downstream envelope once leaves 14.214 s if every intake cost is set to zero, and 5.157 s if intake retains only the earlier optimistic 9.056-second proxy that removes all prefetch and waits. Retaining the observed mixed other-acquisition CPU proxy of 21.650 s leaves a negative 7.436-second detector budget. The 36.308-second full-20-ms rate projection is computed from the existing full anchor envelopes. Relative to that projection, the native work would need to fall by 60.9% with free intake or 85.8% with the optimistic nonzero intake proxy. These figures favor the candidate by excluding its fresh setup and offline verification from the projected budget. They are conditional on the mixed intake proxies and a full-aperture native projection. Only the saved downstream and separately recorded historical raw children were timed.

## DS30-0086 prespecified transfer

The child took 16.736 s wall / 16.114 CPU s through exit. Of that, guarded setup took 0.380 s wall / 0.315 CPU s, and publication took 16.050 s wall / 15.516 CPU s. The native and terminal files appeared at 1.906 and 13.699 s. Offline readback used 1.974 s wall / 1.692 CPU s separately. The original 50-snapshot archive and packet passed the same local admission. This process recorded 153,304 input blocks and 212 major faults, with zero waveform reads. The historical installed raw process was 90.738 s and its verified stopwatch was 91.270 s.

| Scientific measure | Installed | Charted on installed packet |
| --- | ---: | ---: |
| Horizontal error, `c = 0` | 402.304 m | 450.798 m |
| Horizontal error, fitted `c` | 409.842 m | 457.139 m |
| RF RMS, `c = 0` | 130.429135 Hz | 130.432723 Hz |
| RF RMS, fitted `c` | 130.128757 Hz | 130.130802 Hz |

Both owner maps matched exactly at 2,486 owners per arm. The complete numerical grid had all 179 points and the path was independently readable. The numerical grid, path, both positions and terminal differed. All eight actual PNGs decoded and matched their charted manifest. Their byte and RGBA digests differed from the installed figures. The archived installed owner rows and roles are unavailable for an ordering comparison.

The lean proposal passed the initial pair gate on the installed packet. It took 6.383 s wall / 6.332 CPU s before signed-history qualification and evidence, and completed without ordinary fallback. The mixed packet failed the first pair gate, then accepted one repair in 0.181 s wall / 0.174 CPU s. Both paths accepted a signed-history update. On the full packet, that changed the proposed 0.618/0.636 km errors to the published 0.451/0.457 km. The stock-packet solver spent 11.739 s wall / 11.625 CPU s versus 10.571 s wall / 10.456 CPU s on the historical mixed packet. The separately instrumented render calls took 2.590 s wall / 2.569 CPU s and 1.872 s wall / 1.727 CPU s. Verification covers the published named and charted figure bytes and decoded pixels. The geographic gate does not use visual registration.

The half-time target is 45.635 s. After the measured saved publication, the native allowance is 29.585 s with free intake, 19.474 s retaining only the optimistic 10.112-second intake proxy, and 6.719 s retaining the observed 22.866-second mixed other-acquisition CPU proxy. Against the 31.890-second stock-native rate projection, those allowances require 7.23%, 38.93%, and 78.93% native savings. The fastest hypothetical scenario still requires an unmeasured improvement. All allocations are models from measured stages and the full-aperture anchor-rate proxy.

The saved worker kept the exact installed detector SHA and copied its native byte stream unchanged. A generic `20/8 ms` solver-recipe description in the pinned charted witness is inherited from the raw entry. The independently verified native packet, detector hash, inventory, offer and cutoff bind the actual full-20-ms input. Both paid children left the field campaign and its release selection unchanged.
