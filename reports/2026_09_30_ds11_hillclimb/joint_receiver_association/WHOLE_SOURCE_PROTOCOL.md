# Exact whole-source position pilot

The conservative candidate-removal audit is not tractable: some components
retain >1e16 assignments. Do not use a relaxed confidence cutoff. An exact
track-subset dynamic program instead processes one physical satellite at a
time and sums every allowed assignment without pruning. Its real 16-track /
66-satellite support benchmark takes .51 s with synthetic finite weights and
matches independent evidence and derivatives within 5e-14. Unit tests match
brute-force enumeration, normalized priors, source order and sensitivities.

Each track has a physical candidate assignment with its original per-track
catalogue prior. A satellite/RF factor can own any subset of supported tracks;
all observations assigned to that physical source form one union of RX states.
Raw candidates retain their ownership alternatives. Track CFOs remain separate.
This removes the one-track-per-receiver grouping restriction and the prior
catalogue reward associated with forming a matched pair. Disclose that prior
change; zero receiver evidence must equal the independent Doppler mixture with
the same observation ownership. No candidate or track is pruned. Exact DP has
a 16-track-per-RF budget; larger support fails explicitly.

Use the frozen independent receiver calibration first, because it passed donor
transfer and whole-source grouping was its intended calibration unit. No new
beam, correlation, orbit or geographic tuning. This remains conditional on
source detection, with no full absence/clutter model.

Before positional fitting, establish full-source zero-receiver parity and full
finite-difference derivative agreement on scans 0 and 16. Then test original
scans 0/16 and additional scan 1 with the new Doppler-only and signed objectives,
original IID seeds and all prior optimizer/qualification limits. At most 90s
per child. Seal six fits before reference scoring. All are previously exposed
development data at this stage. Require signed improvement on all three versus
both original IID and the new Doppler-only comparator before broader expansion.
Do not promote an isolated gain or reinterpret a timeout as a qualified fit.
