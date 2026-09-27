# Full DS6 numerical CFO inputs

The export is complete: **43 scans, 2,528 tracks, and 113,956 observations**.
Both full-dataset tests pass, including exact reproduction of the earlier four
development inputs. `summary.json` and `SHA256SUMS` seal the completed files.

`protocol.json` freezes all 43 captures in the approved DS6 inventory, the
exporter, and the relevant source implementations. `prepare.py` reads existing
analysis metadata through the public tracking-input and preparation ports. It
does not collect RF, replay raw IQ, or load the roof coordinate.

Each completed `scan-fw-*-plan.json` contains numerical CFO observations,
fractional observation times, receiver/channel identity, candidate IDs, whole
visit groups, causal TLE digest, and source digests. Training masks reproduce
the seed and grouping used by the preceding four-scan comparison; correlated
observations from the same visit remain together. The export retains the
existing three-second/six-observation track policy and its limits. It does not
claim that all detections or all potential physical trajectories are included.

The exporter resumes completed files after checking their protocol hash.
Unavailable numerical inputs are recorded explicitly; integrity failures stop
execution. Completed export is proven only by the full-dataset tests, not by
this README or the presence of a protocol. This dataset is input preparation,
not a positioning result or a sub-kilometre validation claim.
