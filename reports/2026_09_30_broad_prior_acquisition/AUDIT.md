# Independent audit of the merging replay

The final `runs/merging` campaign is complete and internally valid. All 64 units
in the frozen interleaved DS9/DS10/DS11 selection have one terminal launcher
receipt and one sealed native prediction. There are no missing, duplicate, or
unexpected units. All 64 native predictions ended `gate_failed`; none is an
accepted location result.

The audit independently recomputed every prediction seal and every recorded
source, observation, orbit, and compressed state-artifact SHA-256 digest. It
also checked that all receipts use one identical code/configuration binding,
the Sacramento-centered 32-component approximate uniform-disk prior, a
128-component temporary materialization cap, a 32-component retained cap,
coordinates 0--5 for projected merge scoring, a 40,000 pair-evaluation limit,
the 0.1-nat projected-score gate, and the 1% pre-merge discarded-mass gate.

Every scan starts from a fresh normalized 32-component prior with empty history
and zero common clock, receiver drift, and satellite epoch means. Track
selection and overlap exclusions were reconstructed from the evidence's
physical observation IDs. Every checkpoint follows the independently derived
chronological track order, uses the same deterministic at-most-eight sample
selection, and agrees with the final consumed-observation list. Reduction
checkpoints consistently identify their score as
`projected_runnalls_heuristic`, leave the full-joint KL bound null, and stay
within all declared component and pair-work limits.

The blind fitter imports no evaluator or reference coordinate. Its only fixed
geographic input is the declared Sacramento prior center. The campaign source
bindings cover the common adapter, protocol, frozen baseline physics, prior,
runner and selection, the Gaussian-sum core, the merging runner, and the
mixture reducer. The eight batch receipts bind the same protocol and the
expected eight-unit partitions.

The 64 failures contain overlapping gate reasons: 59 position-support
boundaries, 42 projected merge scores above 0.1 nat, 34 intended-region center
boundaries, and 8 cases with more than 1% posterior mass discarded before
merging. There are no runtime exceptions. These counts show that normalization
and moment conservation did not establish broad-prior acquisition; the frozen
support and approximation gates rejected every scan.

The previously audited baseline remains unchanged. Its audit digest is
`sha256:bcd5c87dca0b90b29c3206332f9f5a24b634d6352750600f6f20d8134d05c862`,
and all baseline source paths bound by the final `runs-v3` receipts still match
their recorded hashes. The merging protocol digest is
`sha256:fd40c564c64cc9b801093a1ddaa4b60d22e34619c37e2fdf3a35c6b33d76f8ea`.
The policy freeze digest is
`sha256:8e4bbb854512827cfd0a73aa2b05b48b042a5cc65d83fdcd186e737c0cd9b87e`;
its declared numerical policy agrees with all runtime receipts. The freeze file
itself is not listed in prediction `source_sha256`, so that last agreement is a
present-state audit rather than a receipt-level cryptographic binding.
