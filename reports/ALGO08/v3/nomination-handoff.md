# Reuse exact cold nomination after a lean fallback

## Where the duplicate work occurs

The DS30-0004 lean attempt fell back at `repair_rejection_cap` after 10.472 CPU seconds. Its 5.034 s cold scope included a full catalogue rank and the first two c=0 phase refreshes on all three nominees. The named fallback used the same `previous` orbital context and then independently repeated the ranking and first two refreshes. Its recorded 3.420 s rank plus 1.808 s screen is a **5.228 CPU s ceiling** for that first stage. The screen clock also includes three necessary winner updates and the named acceptance gate. Lean's own prefix construction and all three two-refresh fits totaled 1.408 s. That clock is nested inside the 5.034 s cold scope.

The same saved graph, causal preparation and latest geometry were already available to both routes. The earlier routed worker made one preparation call costing 2.272 s CPU, so there is no second preparation to subtract. Each fresh `ScanLikelihood` separately constructs even its candidate-independent arrays from the same prepared bank and ordered tracks. The `previous` context is identical at cold entry. The `genuine_previous` context uses a different earlier catalogue and mutable per-scan caches. After nomination the routes also use different fit endpoints, masks, signed aliases, family weights and predictive supports. Sharing results of the subsequent conservative, salvage, history or signed stages would require independent equality proofs. Those stages contribute zero to the savings price here.

## Checked handoff

The separate research wrapper uses the existing exact named rank with its catalogue guards as the single producer. It retains all ranked nodes in order, checks that the three completed lean cold prefixes correspond to exactly those nodes, and preserves each finite score, two coordinates and all clipped phase values in ordered label space. The only source rewrite is a reviewed prototype at the installed named screen's two-refresh checkpoint. It delegates all original tie handling, the winner's three remaining refreshes and its original nomination gate to the installed code. It requires the same prepared object, offered region and native bound, the original noise SHA, the `previous` role, and a numerical fingerprint including the actual prepared track bank, causal catalogue/time data and orbit array layout. A changed input or role builds and runs the independent named nomination. Unsupported, nonfinite, stale, out-of-order or incomplete checkpoints do the same. No terminal, later fit or surveyed position enters reuse.

The standalone entry keeps the prior bytes of `history_risk_route.py`, `joint_publication.py` and `cold_finalist_race.py`. Select it only in a research worker by substituting `nomination_handoff.routed_binding` for the existing `history_risk_route_trial.binding`. Existing launchers and their source pins are unchanged. Thirteen component checks cover exact ties, retained state, unused/missing ranks, incomplete and invalid checkpoints, and changes to earlier orbit, prepared array, offered region or native bound. [Prototype](nomination_handoff.py) · [Component tests](../../../tests/pipeline_eval/test_nomination_handoff.py)

## One authenticated nomination slice

The slice retained all seven ordered rank results, captured three complete prefixes and ran only the three outstanding winner updates. The ordered screen scores were **20232.752956449876**, **20139.593873590456**, and **20726.47221676162**. These matched the fresh named worker and earlier routed trace exactly. The installed tie rule selected zero-based rank 1 and produced the original completed c=0 score of **20137.548092817044**. The real post-nomination gate accepted 58 of 83 tracks.

The producer took **4.452315 CPU s**, including 2.963349 s on the exact rank. Resumed nomination through the final gate cost **0.420248 CPU s**. The two geometry checks totaled 26.880 ms and checkpoint capture took 6.527 ms, both inside the measured producer/resume clocks. Scope setup added 0.758 ms CPU. Subtracting the resumed stage from the earlier 5.228216 s paid rank and screen gives a **4.808 s historical fallback-site estimate**, with constructor clocks left out of that older sum. It does not establish through-exit savings. The as-run slice temporarily passed the checkpoint callback through the original research helper. The standalone wrapper captures the same return at that helper's scoped call boundary. [Frozen slice](nomination-handoff-protocol.md) · [Slice receipt](measurements/nomination-handoff-0004-slice.json)

## Complete saved publication with the standalone wrapper

The saved candidate exited zero and reproduced the named terminal, 3,430 owners in the same order in each calibration arm, the complete 179-point grid and path, and all eight PNG and RGBA digests. The equal geographic errors are 184.741 m fixed and 103.808 m fitted. The corresponding RF RMS values are 133.338901 and 133.335131 Hz. The candidate passed the same repair rejection and paid the original named stages after nomination. The actual fallback reused the previous context and ordered rank once, with all three original two-round prefixes and no new named prefix evaluations. [Frozen saved publication](nomination-handoff-publication-protocol.md) · [Scored complete receipt](measurements/nomination-handoff-0004-publication.json)

| Complete saved child | Elapsed s | CPU s |
| --- | ---: | ---: |
| Installed direct named | 44.759996 | 44.660305 |
| Earlier history-risk route | 54.783043 | 54.321742 |
| History risk with exact handoff | 47.737931 | 47.692269 |
| Handoff child plus new admission | 48.147703 | 48.100263 |

Through exit the handoff candidate saved **7.045 s elapsed and 6.629 s CPU** against the previous history-risk route. It remains **2.978 s elapsed and 3.032 s CPU slower** than direct named. Earlier controls ran in a separate slot. The earlier routed worker recorded 16 input blocks and one major fault. The candidate and direct named recorded zero of either.

| Scope, CPU s | Earlier routed | Exact handoff | Earlier minus handoff |
| --- | ---: | ---: | ---: |
| Cold producer, inside lean attempt below | 5.034278 | 4.215953 | 0.818325 |
| Lean attempt before fallback | 10.472155 | 9.178312 | 1.293843 |
| Named fallback including standard evidence | 36.860411 | 31.458221 | 5.402191 |
| Remaining process work | 6.989175 | 7.055737 | −0.066562 |

The new producer actually paid 2.810142 CPU s for the exact rank, with 26.798 ms total input verification and 6.329 ms checkpoint capture charged within the complete route. The corresponding one-slice producer was 4.452315 s, compared with the earlier original lean scope of 5.034278 s. The new route uses the verified grouped rank and has a different execution date. The measured cold and fallback deltas therefore include implementation differences and run variation. The cold row is a substage of the lean attempt and must not be added again. Preparations were 2.272 s CPU earlier and 2.352 s with the handoff, one call each.

The complete replay used only the existing signed detector and staged causal snapshots. No waveform or backing archive reads were permitted. The offline comparison authenticates the eight published sidecars and numerics against the earlier direct named worker, without running another solver. Its initial attempt used the older installed storage import because the sparse checkout lacked `src`. Restoring `src` to the checkout corrected that read-only verifier. The candidate clock and output remained as written. [Launcher and verifier](nomination_handoff_publication.py)

To reproduce, include `src`, `tools`, `reports/ALGO08/v3` and `tests/pipeline_eval` in the research checkout and use the existing staged DS30-0004 request. Run `nomination_handoff_publication.py launch FRESH_TMPFS_ROOT` with the installed `-IB` interpreter at nice 15, CPU 2, I/O priority 7 and single numeric threads under the Gauss lock. Then run its `score` mode against the same root. The archived slice was produced from `4dad4b0c1`. The complete standalone runtime freeze was `b93b7b482`. Receipt SHA-256 values are `5e91cd497cb61a875e26ee19f950bf82406cf42fecdf0623c13e17cd39408ae2` for the slice and `a32995249cd1b03f1c0383eb754f712ea5d997e041c62feed7f99a1e64715a6b` for the full saved run.
