# Transfer protected local repair to the existing missing-region offers

Use the short receiver outputs already sealed for public north and south. Replay the original ±100 m mirror offers and both far 52.5 km omissions. Include the original containing offer at each site with the same saved source packet. Freeze the offer file, archived decision and causal catalogue before launching the fits. The historical northern omission controls used forward continuation. The closest archived southern misses use the genuine unfiltered short detections and the reviewed regional-track scorer. A fresh forward-only replay on each offer isolates the repair from these differences.

| Offer | Offer SHA-256 | Historical decision |
|---|---|---|
| North, containing | `f4ff743e9f3d00bc18344143bffaaf7801276018dbd75b6ab2ec5207e887e891` | Fix |
| North, 100 m omitted | `eacc9fd6b5da3e9e38a7b13edee43aad63e229622c9973aa401a2dbb8c7f20d7` | False fix |
| North, 52.5 km omitted | `6b48044ea39e5a32611da86c0aebe3efb922d072773456da3d9d75de9b687ed4` | Withheld |
| South, containing | `471704a6dfcfd4acdb72f3aacae638fe8f6ae6a796b01dd59cfd3d7a9d92610c` | Fix |
| South, 100 m omitted | `0c89bd52594b706b2772fbcf6ea627065eeb3d94eb6266f35de09ebb6b7a5d2a` | False fix |
| South, 52.5 km omitted | `a5127d5844ca98f58a157ec2b6b962f60ec2894c58b8122a0ee244b248a5eb62` | Withheld |

Run the protected branch exactly as `d3765b4b5` with its existing fixed-owner rules and both calibration arms. Use its installed graph, full cold catalogue, joint signed finish, causal archive, prepared regional handoff, native geographic projection and regional track scorer, exact cold-row and predictive-phase-state reuse, ordinary grid and standard publication. The matched control uses the same saved handoff and forward selection with the repair callback disabled. Alternate order across the sequence north near, south near, north far, south far, north contains, south contains. Each opens a fresh output directory. Record early geographic exits even if the repair cannot run, any repair or veto decisions and reasons, both calibrated terminal estimates or two null arms, owner/role differences, complete grid and path, objective replay, all reported PNGs and process and solve times. Use the same post-publication scoring function as the donor. Release reference coordinates only after all pairs have sealed. A false fix fails an omitted-region control regardless of the point’s error relative to the hidden receiver. Use the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. No new I/Q reads, signal collection or threshold changes.

[Donor rule](local-future-repair-protocol.md) · [North development omissions](north-causal-transfer.md) · [South development omissions](full-short-transfer.md) · [Regional scorer](regional-track-scores.md)
