# Independent outcome review

Reviewed the sealed amended final-TEST artifacts after execution. This review
did not run another fit, choose an alternative configuration, or access a
replacement cohort.

The execution amendment is SHA-256
`80c8f7b03e696c7c4285da3da22377443042d6dd35ea2be8faeca7e8a2f46f6a`. It
preserves the original membership freeze and validation selection, binds the
receipt manifest, and authorizes only the already-declared 1/6/16 prefixes
while retaining the 64-session arms as failures because frozen session 48
(`scan-hop-6cd2560365a058bc`) lacks counter-continuity authority.

All companion seals verify:

| Artifact | SHA-256 | Accounting |
| --- | --- | --- |
| Baseline | `df7467db9a912a1005f1877ab604a3bd2ad6d1f1b523719c34d9d53f22cf54e5` | 6 prefix successes, 2 explicit 64 failures |
| Timing | `bf38ded88d5254da1aad9fd7a75eccb551bb5c0281573f0f924e4cf27e554c2c` | 6 fits with accepted stopping and zero visibility failures, 2 propagated failures |
| Outcome | `2e365ef449bbd419c93b845310bad7abe41c1435584a345920b8a8025d30ed2e` | 6 post-seal rows, 2 retained failures |

Each artifact binds the immutable freeze, receipt-manifest digest, and
amendment; timing additionally binds baseline and results additionally bind
timing. The amended source hashes match the amendment: baseline
`a2dbf969553b3f94abb9e926c632df1b29bae6abbdb82a92b141f82110fd1052`, timing
`1d5812e9e6362b1ceaf4d9d35910ccb703af87593a5316fa3e76ed8b00e270c6`, and
evaluator `d5d04d0fba11f8f733310e6f05e1e258d602fdecab31b9c33a655c7d7596e97d`.

No row is sub-300 m. The closest partial-view post-seal reference result is
the 16-scan Sacramento arm at 3.348 km (the matching Reno arm is 3.348 km).
Those two locations agree because their fitted solutions coincide to displayed
precision; this is not independent replication. The 64-session TEST outcome
remains failed/ineligible, so the partial views cannot establish final TEST
accuracy or support a broad claim.

One documentation correction was requested during review: the original README
described the pre-amendment export abort and said no inference artifacts
existed, whereas the approved amendment subsequently created the sealed
partial-prefix artifacts above. The final narrative must distinguish those two
states.
