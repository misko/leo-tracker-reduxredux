# Compact secant on arbitrary offered tiles

**Compact secant issued both containing fixes on the two previously unseen geometries.** Errors ranged from 0.83 to 1.27 km across both calibration arms. Both omitted-offer runs reached the deadline during conservative recovery. The matched native clock/offset control issued one containing fix and withheld both omissions. The compact wrong-region decision remains unmeasured on these cases.

The portable worker combines the established arbitrary-tile native preparation with the same compact projector and bounded secant optimizer used in the 135-recording compact study. The optimizer, orbital relinearization and association/cavity policy are fixed. Both the sky screen and search tile use the supplied center. The clock-transfer control builds its own anonymous Graph and uses the shared single causal TLE. Compact secant requires its additional authentic prior TLE collection history. [Compact study](../../secant-full/README.md) · [Portable input parity](../../portable-v5/README.md) · [Predeclared protocol](PROTOCOL.md)

The test selects the two existing 25 km containing offers with the greatest center-to-center distance from the scored six-site clock-transfer panel. This gives locations in East Asia and South America, separated by 17,066 km at the offer centers. It retains their original and far-omitted offers. No compact outcomes informed selection. The scores are a new replay of existing simulated captures. An independent plumbing check uses authentic DS26-0036 native observations and a supplied center shifted 7 km east of the original measured-roof offer. [Previous clock transfer](../../recovery/clock-transfer/README.md)

## Input compatibility

The exact simulated factor archives already supplied the UTC midpoint, sample counters, receiver/visit timing, actual RF, folded CFO and fractional frame epochs. The v5 native contract also requires a qualification flag, monotonic clock bracket, delivery clocks and provenance. The adapter supplied these from the simulator's sample schedule, starting its monotonic axis at 10 s and placing each delivery at the end of its original probe. No sample counter, detector factor, realtime anchor or acquisition duration changed. The simulated probe clocks are controller output. The separate measured query uses its authentic measured delivery clocks and clock authority.

The exact single causal TLE was the last available received catalogue for each simulated query. The portable input added only authenticated prior archives in the 72 h window. The East Asia case used 36 collections and 32 distinct payloads, South America 35 and 29, and the shifted roof 38 and 27. The solver's preceding-element view uses at most 48 h and the phase-history estimate uses the original 72 h window. Each relocated controller process only received its own past-only catalogues, native probes and one offered tile. Scoring coordinates, planted orbit identities and later trajectory TLEs were absent. [Bound requests](requests.json) · [History inventory](history-inventory.json) · [Program hashes](source-lock.json)

## Simulated containing and omitted offers

Every paired cell follows `c = 0` / fitted `c`. The compact secant worker used the same starting candidate sets and numerical policy in both arms. Position errors compare to the simulator's released location. The compact in-fit RF statistic and native held RF statistic measure different stages and are shown separately.

| Query | Compact secant position error, km | Native clock/offset position error, km | Compact worker wall time |
|---|---|---|---:|
| East Asia, containing | 1.158 / 1.272 | Withheld / withheld | 140.09 s |
| South America, containing | 0.939 / 0.833 | 1.797 / 1.787 | 122.72 s |
| East Asia, omitted | Deadline / deadline | Withheld / withheld | 229.17 s |
| South America, omitted | Deadline / deadline | Withheld / withheld | 225.14 s |

The 225 s supervisor interrupt took up to 4.17 additional seconds to return on shared, low-priority cores. Both omissions reached conservative recovery before interruption. No location was issued or scored from partial fits. The native clock/offset control had a completed decision on all four offers, with no omitted publications. Its forced estimates stay diagnostic. [Sealed predictions](prediction-lock.json) · [Position and RF results](scores.json)

Compact in-fit RF RMS was 68.339 / 68.264 Hz in East Asia and 72.322 / 72.309 Hz in South America. Fitted `c` lowered the RMS slightly at both sites, while position error increased by 0.115 km in East Asia and decreased by 0.106 km in South America. The native control's held RF RMS was 263 / 279 Hz in East Asia and 196 / 203 Hz in South America. The two compact containing calls constructed 24 and 25 anonymous tracks, 1,093 and 1,069 winning observations, and 8,396 and 7,282 historical orbital transitions, respectively.

[Position figures, zero calibration](figures/c0/transfer.pdf) · [Position figures, fitted calibration](figures/fitted_c/transfer.pdf)

## Authentic shifted tile

The original measured launch stopped at an import error before numerical preparation. A shared CLI module had gained a new dependency after the two synthetic workers started. The retry bound immutable copies of that module and its support imports, then sent the exact original measured request bytes. The frozen secant solver, actual receiver clocks, causal history and shifted offer matched the primary request. The retry completed preparation and initial position selection, entered conservative recovery, and reached its 225 s deadline. The shifted query verified the generic input and search path through that stage. A measured publication and geographic accuracy remain unmeasured for the shifted tile. [First prediction seal](prediction-lock.json) · [Measured retry](measured-retry/prediction.json) · [Retry seal](measured-retry/prediction-lock.json)

The first launcher-only attempt for the complete roster is separately preserved. Its diagnostic stage wrapper looked up the recovery function in the wrong module and failed before model execution. The corrected main replay uses the same frozen optimizer and evidence. [First launcher receipt](adapter-launch/prediction-lock.json)
