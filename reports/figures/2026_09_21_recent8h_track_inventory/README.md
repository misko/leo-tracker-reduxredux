# Recent eight-hour adaptive-track inventory

This inventory freezes the inclusive `captured_at` window
`2026-09-21T06:34:16Z` through `2026-09-21T14:34:16Z`. It is a metadata-only
read of the local API history and immutable manifests beneath `/srv/bulk/leo`;
no IQ was decoded and no RF collection was performed.

The window contains 79 adaptive captures from `radio_pluto_19f2`. Seventy-five
have complete `scanner-shared-tracking-v14` products containing 2,914 published
tracklets. Four captures have no published tracking product:

- `scan-hop-9ab2620eb9b79351`, captured `2026-09-21T14:12:16.424975Z`
- `scan-hop-b89bc4be5e52c033`, captured `2026-09-21T14:18:16.422219Z`
- `scan-hop-e62070d6a4a5b493`, captured `2026-09-21T14:24:16.285223Z`
- `scan-hop-5878893927a7b8f9`, captured `2026-09-21T14:30:16.308904Z`

## Interpretation

An RF track in this inventory is admitted only when it appears in a complete
v14 trajectory product, meaning it passed the frozen, TLE-blind reconstruction
gates. No confidence percentage is invented. Catalogue abstention is reported
separately because it concerns identity stability, not RF trajectory quality.
Every product remains `candidate_only=true` and `identity_claimed=false`.
V14 does not persist a per-track maximum-gap field, so this inventory does not
infer one.

The longest tracks are:

| Rank | Session | Tracklet | RX | Lane | Span (s) | Observations | Catalogue disposition |
|---:|---|---|---:|---|---:|---:|---|
| 1 | `scan-hop-01b11a5d776e7369` | `sha256:d6d1c6204fcb7722fef81f3aeb8080b465c8b75a8caa869b9423e052e7eaaae3` | 1 | 2 lower | 64.789610 | 124 | abstains; RF track retained |
| 2 | `scan-hop-56b26a40cfeca91f` | `sha256:500c5e08f730f93c18be6c4e27aa6711c9e5d263fe5c80e66fe7a8bb13d42d9b` | 1 | 1 lower | 58.313131 | 188 | abstains; RF track retained |
| 3 | `scan-hop-1bec690f93ce0b1e` | `sha256:da95dd5b55dbec8c7f485a00334d0c926ffc34d7ecb448dbc8c5485875fbe52a` | 1 | 4 lower | 58.297451 | 99 | does not abstain |
| 4 | `scan-hop-e46d3aba244cf641` | `sha256:78c307f35318463a89d69c38f2b648d13bf892efaf11810f153bc09b8ddf2173` | 1 | 2 upper | 57.437826 | 141 | does not abstain |
| 5 | `scan-hop-3f353f6f0c7a9852` | `sha256:f481497b993f462eb5327f9474df99e6b2a96bc4b753662c1d761a4ea55a5f97` | 1 | 3 lower | 54.862923 | 73 | abstains; RF track retained |

## Dual-receiver phase shortlist

`top5_dual_shared_visits.json` contains the full RX0/RX1 track IDs, authority
digests, shared visit indices, and observation-ID pairs for the five longest
verified simultaneous pairs. Their exact shared-visit counts are 101, 106, 49,
69, and 68 respectively. These recordings use 2.5 MS/s, radio serial
`10400056f695001322002d0010ad1719f2`, fixture `LT3D-001A`, and geometry binding
`sha256:55e5a117d885e8ac158a0a41895b66cb5be881d66630d2765fccf5711a21643f`.
The declared saved-IQ chunks are present for every ranked row; the counts and
absolute recording and tracking manifest paths are included in both ranked
files.

## Double-difference screen

The metadata screen examined all 75 complete products for two distinct
persisted catalogue physical groups containing RX0/RX1 tracks on the same
channel and edge with overlapping support. It found none. This covers only the
bounded catalogue groups persisted by each product. Since `group_limit=4` and
many products contain more RF groups, it does not exclude a same-visit reference
among unpublished RF groups. Exact reconstruction of the five longest dual-RX
pairs also found no four-distinct-track, same-channel/edge combination sharing
at least two visits. Cross-channel UTC overlap is ineligible because the adaptive
radio uses one LO setting per visit.

Files:

- `ranked_tracks.json`: complete ranked inventory, criteria, counts, missing products, and provenance
- `ranked_tracks.csv`: flat 2,914-row summary
- `top5_dual_shared_visits.json`: exact shared-visit and observation references
- `persisted_group_dd_screen.json`: all-product persisted-group screen and its explicit limits
