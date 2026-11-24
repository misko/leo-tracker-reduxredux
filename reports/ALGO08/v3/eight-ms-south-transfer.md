# All-visit 20/8 ms receiver on the original South simulation

The live South candidate finished in **10.466 s**, compared with **10.685 s** for the archived guarded 20/12 ms run and **14.370 s** for named ALGO08v3. Both position errors improved against both controls. RF RMS increased in both arms. The same signed packet still produced a false fix on the original offer that excludes the receiver by 100 m. [Frozen procedure](eight-ms-south-transfer-protocol.md) · [Sealed receipts](measurements/eight-ms-south-transfer.json.gz)

| Offer and receiver | Geographic outcome | Horizontal error, km | RF RMS, Hz |
| --- | --- | ---: | ---: |
| Containing, named v3 | Fix | 0.817 / 1.101 | 6.502 / 6.392 |
| Containing, guarded 12 ms | Fix | 0.553 / 0.824 | 6.075 / 5.975 |
| Containing, live 8 ms | Fix | 0.325 / 0.363 | 10.213 / 10.108 |
| 100 m omitted, named v3 | False fix | 0.817 / 1.102 | 6.502 / 6.392 |
| 100 m omitted, guarded 12 ms | False fix | 0.554 / 0.824 | 6.075 / 5.975 |
| 100 m omitted, saved 8 ms | False fix | 0.325 / 0.363 | 10.213 / 10.108 |

Each pair is ordered `c = 0` then fitted `c`. On the containing offer the candidate improved by 491/739 m against named v3 and 228/461 m against guarded 12 ms. Relative to guarded 12 ms, RF RMS increased 4.138/4.134 Hz. On the candidate's common inputs, fitting `c` reduced RF RMS by 0.104 Hz while horizontal error increased 37 m.

## One original raw acquisition

The unchanged all-visit mode used 304 installed two-scan 20 ms anchor calls and 2,096 pinned 8 ms primary calls. It authenticated the exact original 1,200 visits, both radios, 1,574,298,988 compressed bytes and 1.920 GB decoded. All 384,361 compressed payload pages and 188 index pages were resident before and after. There were zero process major faults and zero input blocks. No conditioning, staging, alternate physical backing source or second raw South launch was needed. The measured 70 anchor and 1,276 short factors supplied the original EOF selector. It preferred history, with held gains of +76.947/+66.141 nats, retaining 456 factors and making no CFO-tail calls. The selected packet has SHA-256 `f0982e61080ddff6ff98ba4215dff03c12eb1260e19b5cbd23bea711724487a9`.

The same 456 signed observation slots were selected by guarded 12 ms. Changed CFOs affected 396 slots, 198 per radio, with 16.564 Hz RMS difference and a maximum of 38.569 Hz. The integer epoch field changed by one sample on 77 rows and the fractional offset changed on 396. Every original opportunity and hardware clock matched. The 8 ms fit kept all 266 named owners and added 38 in both arms, with unchanged satellite and role on shared rows. Against guarded 12 ms, it shared 262 owners in each arm, removed 28 and added 42. Every shared satellite and role remained unchanged.

| Containing clock | Named v3, archived | Guarded 12 ms, archived | Native 8 ms, fresh |
| --- | ---: | ---: | ---: |
| Process CPU / elapsed, s | 14.179 / 14.370 | 10.681 / 10.685 | 10.465 / 10.466 |
| Authenticated acquisition CPU, s | — | 5.135 | 5.011 |
| Held selector CPU, s | — | 0.035 | 0.064 |
| Decision and publication CPU, s | — | 4.966 | 4.887 |
| Numerical solve CPU, s | — | 3.247 | 3.208 |

The 8 ms native anchors and primaries used 0.757 and 1.843 CPU seconds inside acquisition. The observed through-exit difference versus guarded 12 ms was 0.218 s. These are single launches with historical controls. The fresh result is 1.37× as fast as the archived named v3 clock and remains 3.281 s above half of that clock. [Guarded South acquisition](combined-raw-south.md) · [North all-visit 8 ms control](eight-ms-native-live.md)

## Original 100 m omission

The saved worker verified the identical native bytes, used the original signed inventory through one handoff, and opened zero waveform bytes. It exited in **5.333 s elapsed / 5.330 s CPU**. An initial 0.052 s saved launch failed before importing the installed contracts and made no handoff, waveform call or solve. After correcting the import order, exactly one saved numerical solve ran. Its result remained a false fix. The estimated positions were 220/251 m inside the offered face. Moving the face between its containing and omitted locations moved the two estimated positions by only 0.039/0.398 m.

Both candidate publications kept the same 304 ordered owner rows in each calibration arm, 423 graph points and 29 tracks. Both used 240 compact rank profiles, 11 portable archive bodies and 24 regional probes. The regional routine stopped at `eligible_exterior_separation`, returned no withhold, and the named final fit was accepted in both cases. Each publication's complete 137-point matched grid and path bind its verified position PNG. All eight figures per offer passed encoded and decoded checks. The two saved and raw clocks have different boundaries. Five focused tests passed. [Earlier exact-offer guarded omission](south-raw-offer.md)
