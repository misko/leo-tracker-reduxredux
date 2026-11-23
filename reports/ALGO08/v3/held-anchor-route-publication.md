# Held-anchor selection through cumulative publication

The cumulative CLI now accepts `--held-anchor-route`. It completes one authenticated 20/12 ms receiver pass, seals a route decision, and hands the selected signed packet to the normal publication once. On the prospective saved DS30-0008 input, both radios favored the unfiltered route. The single fresh publication completed with the same terminal, owner rows, numerical evidence, and eight PNGs as the previously published ordinary-Graph unfiltered result. [Frozen protocol](held-anchor-route-publication-protocol.md) · [Prospective dense receipt](measurements/held-anchor-route-dense.json.gz)

## Selector and ancestry

The opt-in calls the frozen `select_route` from `4b02d2b19`. The released continuation sees all original full anchors as timed empty opportunities during training. Each complete eight-visit cycle contributes seven donors on the same radio, edge, channel and exact RF. The two routes' Bernoulli predictions are then scored against the untouched held anchor. History wins only when the summed improvement is strictly positive on both radios. Ties, sparse evidence and disagreements retain the original packet. Route selection has no location, reference, operator offer, orbit or solver input. [Frozen held-cycle study](anchor-cycle-route.md)

The original unfiltered detector identity remains `13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40`. A history win restores the same released continuation on the complete original chronology once and verifies its existing recipe `96b04d7718969d10b87dc1baa86c8d406e963c7e54ede8f6fd71aa54b7ac3569`. Original lane metadata and any retained signed factors are checked exactly. The decision sidecar binds original and selected detector and packet digests, raw authority, inventory, settings and measured costs before the solver is invoked. The raw CLI consumes neither a prior publication nor old scores to make the choice. [Normal CLI](unified_short_bootstrap.py) · [Checked selection adapter](held_anchor_route_publication.py)

| Input | History gain by radio, nats | Route | Verified selected factors |
|---|---:|---|---:|
| Saved North simulation control | +28.366 / +26.345 | History | 456 |
| Saved weak DS30-0016 control | −15.273 / −8.948 | Unfiltered | 475 |
| Saved medium DS30-0057, independent sealed replay | −29.002 / −43.663 | Unfiltered | Previously sealed result |
| Prospective saved dense DS30-0008 | −117.994 / −63.989 | Unfiltered | 7,336 |

North's selected packet matches the previously sealed genuine raw history packet at `a03fefaf84057a282a0868ae8a52d34099f530dcf69220360147389e110523c3`. DS30-0016 retains `c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589`, with no full-history replay. Both control checks completed before any dense selection. The control adapter loaded no scientific publication modules while choosing the route. The tiny incomplete-cycle test also retains the original identity and stages no full history. [Exact saved controls](measurements/held-anchor-route-controls.json)

## Prospective dense publication

The sealed choice retained original packet SHA-256 `ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85`. The scorer consumed **0.161 CPU s** and the complete selector adapter through pre-seal bookkeeping consumed **0.217 CPU s**. The seal was written before the solver and before any current position or historical truth were opened. As the selected packet and current unfiltered control were identical, the preregistered driver launched one fresh publication. Its exit clock was **28.516 s elapsed and 28.508 CPU s**, of which **24.290 CPU s** was the numerical solve. It used the ordinary Graph, current regional and cold stages, exact predictive handoff and explicit web layout. The regional proof evaluated 25 probes and stopped at `inside_score`. The verified standard publication included **179 complete grid points**, two independently bound position sidecars and **eight decoded and hashed PNGs**. [Saved execution and audit](held_anchor_route_dense.py)

| Calibration | Horizontal error | RF RMS | Final owners |
|---|---:|---:|---:|
| `c = 0` | 0.919 km | 140.961 Hz | 4,367 |
| Fitted `c` | 0.857 km | 140.950 Hz | 4,367 |

The ordered owner and role digest, terminal, position arms, grid and path agree exactly with the archived ordinary-Graph unfiltered publication. All eight encoded PNGs and decoded RGBA arrays also match that publication. That earlier run used different joint publication and grid phase-state source digests and took 28.162 s through exit and 23.769 CPU s in its numerical solve. The current and earlier clocks describe separate sessions. This experiment measures the selector overhead and the one saved publication the selected route incurred. It does not establish a speed gain over a matched alternate route for dense. [Archived ordinary-Graph publication](cumulative-dense-graph.md)

## Geographic limits

The earlier South simulation selected history. Relative to unfiltered, horizontal error increased by **124 m** with `c = 0` and **273 m** with fitted `c`, even though both history errors were below those of installed v3. Both routes published false fixes on the historical North and South **100 m omissions** and withheld on both **52.5 km omissions**. These are existing development results. This dense saved experiment made zero waveform calls and supplies no new near-edge, raw timing or release qualification evidence. [Archived geographic outcomes](anchor-cycle-route.md)

## Reproduction

The CLI integration is `0d0b2ad9f`, the saved dense driver is `9069d2ea7`, and 16 component and adjacent tests passed. Under the one low-priority Gauss lock, run `held_anchor_route_controls.py` against the fixed archived controls. Then pass a fresh tmpfs root and the independent medium pre-reveal receipt to `held_anchor_route_dense.py`. The receipt used `/dev/shm/leo-anchor-cycle-sealed-before-reveal.json` at SHA-256 `c886afae2bc5ef5e5a63b01ac2577fa56127878c408cb698be4c1e6e1fd58ab5`. It can be reconstructed from [the sealed selector audit](measurements/anchor-cycle-route.json.gz) by keeping exactly `cases` and `machine`, with sorted keys, two-space indentation and one final newline. Run as the existing capture-read account using the pinned installed release with `PYTHONPATH` including this checkout, its `src` and the release paths. The saved worker denies waveform and detector calls. [Tests](../../../tests/pipeline_eval/test_held_anchor_route_publication.py)
