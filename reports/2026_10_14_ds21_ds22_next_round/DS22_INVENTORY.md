# Frozen DS22 evaluation population

The new inventory is frozen and verified without preparing observations,
running inference, or reading localization errors. It retains all 137 original
whole recordings and all 69 eligible fast CH1–8 recordings, including the one
without a pinned tracking input.

| Fast population | Development | Locked evaluation | Total |
|---|---:|---:|---:|
| Eligible | 45 | 24 | 69 |
| Pinned tracking input available | 44 | 24 | 68 |
| Input unavailable in authority snapshot | 1 | 0 | 1 |

DS22-137 has no session identity or pinned tracking input in this snapshot.
It remains an explicit unavailable case rather than disappearing through a
session-name filter. Existing raw recordings are preserved; no RF collection
was requested or performed.

Seed 20261014 randomizes the 35 whole UTC-hour acquisition groups across all
137 fast/adaptive members before checking input availability. Twelve hours are
locked. The full-format allocation is 89 development and 48 evaluation members;
the fast subset above is the localization target.

Verification checks the published manifest digest, evaluation-unit seal and
exact member identities, every pinned tracking snapshot, the original input
adapter bytes, and the frozen inventory's own source/archive and membership
replay. It does not claim a fresh hash of all compressed IQ or every mint file.
The regional prior and adapter match the established DS21 analysis inputs.

Membership SHA-256:
`0a447856091ef3fb3bae1d4dd731321175e25189e324de2e06a069bde082681e`.
Authority manifest SHA-256:
`705380facbea54e6a1142eab07f1114f7ae99d3066e4f8bd9210cb55014768f3`.
Local namespace: `local/ds22-inventory-v1` in this report directory.
Nine offline tests passed independently before the real inventory freeze.

The next adapter must preserve genuine DS22 authority and reject locked
members during development. Existing shared-proposal half-band results are
distinct from the independent band-only initialization controls required for
the final combined-versus-half comparison. No DS22 accuracy result exists yet.
