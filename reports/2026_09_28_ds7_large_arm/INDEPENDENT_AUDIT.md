# Independent ARM recovery audit

This audit reads the frozen full-original rows and the completed physical-ARM
rows directly. It does not import or invoke the report's main scorer. All 704
cases are unique and bound to the same input manifest. Each original case has
the expected 22 receiver-windows. Each executed ARM receiver-window contains
at most one candidate, so identity recovery uses a direct any-match check.

An original candidate is positive at margin `>= 0.025`. An ARM candidate is
positive when fractional refinement completed and its margin is strictly
`> 0.025`. Identity requires the same case, receiver, and window; epoch distance
at the case's native sample rate no greater than 2 microseconds; and tracking
CFO distance no greater than 8 kHz.

| Rate (MS/s) | Cases | Original positive windows | In ARM rank-6 | Executed | Positive again | Identity recovered | ARM positive candidates | Original positive candidates | In rank-6 | Executed | One-to-one candidate recovered | Executed candidate misses |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.5 | 152 | 1,682 | 920 | 150 | 138 | 126 | 191 | 4,573 | 2,478 | 407 | 126 | 281 |
| 5.0 | 216 | 1,874 | 1,023 | 169 | 148 | 144 | 188 | 5,466 | 2,990 | 507 | 144 | 363 |
| 7.5 | 184 | 1,933 | 1,042 | 175 | 133 | 126 | 162 | 5,186 | 2,822 | 483 | 126 | 357 |
| 10.0 | 152 | 1,518 | 833 | 141 | 103 | 103 | 120 | 4,356 | 2,389 | 393 | 103 | 290 |
| **Total** | **704** | **7,007** | **3,818** | **635** | **522** | **499** | **661** | **19,581** | **10,679** | **1,790** | **499** | **1,291** |

The ARM arm ranked 8,448 windows and executed 1,408 windows in total, exactly
12 ranked and two executed windows per case. Of the 635 executed windows that
were positive in the original, 522 were positive again and 499 contained an
identity-matched candidate. Enforcing one-to-one recovery gives 499 recovered
candidates and 1,291 misses among the 1,790 original positive hypotheses in
executed windows. Against all 19,581 original positive hypotheses, including
windows the reduced ARM workload did not execute, 19,082 are not recovered.
As a secondary diagnostic only, allowing one ARM candidate to associate with
every duplicate original hypothesis inside the identity gates produces 1,083
many-to-one associations. Those associations are not candidate recoveries.

Exact source hashes, assertions, per-rate counters, gates, and machine-readable
totals are recorded in `INDEPENDENT_AUDIT.json`.
