# How often the published ALGO08v3 fix used orbit-history recovery

**DS30-0160 is the only named-v3 fix in the signed 100-recording panel published with the history-support orbit policy.** All 91 other named fixes used the stock orbit policy. The prospective rule for choosing a second history-support control returned no case. Existing releases have separate evidence for the five numerical failures. Those runs and the three withdrawals have no completed terminal policy in this count. [Prespecified selection](history-retry-roster-protocol.md) · [All signed receipt and terminal identities](measurements/history-retry-roster.json)

| Original panel | Named fixes | Completed with stock orbit policy | Completed with history support | Withheld / solver failed |
|---|---:|---:|---:|---:|
| First 4 | 4 | 4 | 0 | 0 / 0 |
| First 16 | 15 | 15 | 0 | 0 / 1 |
| All 100 | 92 | 91 | 1 | 3 / 5 |

An improvement limited to successful history-support replays has a clear correctness role on DS30-0160. If the successor takes the same policy on the original named detector input, that improvement alone provides zero direct time savings on the completed cases in the first four and sixteen. A different receiver or different satellite assignments can trigger a different orbit policy. This audit does not measure those future branch frequencies. The same physical archive cannot establish transfer of the recovery decision to another location.

The census verified the frozen panel and final decision, all 100 named pair receipts against those published hashes, the named release specification, and every completed terminal against its own signed digest and session. Pair and terminal reads totaled 1,919,635 metadata bytes. Only the decision, orbit policy and provenance hashes enter the result. Original I/Q, chart images and solver outputs beyond the terminal were unnecessary. [Replay](history_retry_roster.py)
