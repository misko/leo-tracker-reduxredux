# Post-commit observer hardware soak

Date: 2026-08-19 UTC  
Soak ID: `post-observer-canary-20260819-001`  
Evidence root: `/srv/bulk/leo/qualification/soak/post-observer-canary-20260819-001`

This bounded dual-Pluto run qualified the production soak's per-trial catalog
observer before starting the 24-hour gate. It used the ordinary 60-second,
2.5 MS/s, two-receiver profile and the production RecordingStore, PostgreSQL
catalog, reconciliation, and Standard processing queue.

The immutable summary completed with `passed=true` and no policy violations:

- 2/2 trials committed; 600,000,000 captured samples;
- 120 seconds of sample-derived recording in 144.772 seconds active time
  (82.889% duty while the RAID6 resync was active);
- valid bundle digests, zero reported gaps, zero reported overflows, and zero
  false-complete outcomes;
- minimum estimated paired overlap fraction `0.9999864133`;
- 2/2 post-commit callbacks succeeded;
- each new session was registered immediately and queued one Standard run;
- the measured backlog rose by exactly 60 stage jobs, from 218 to 278;
- peak RSS growth was 259,842,048 bytes, below the 512 MiB policy limit.

The overlap value is an estimate, not a coherence or no-loss claim. Pluto does
not expose a device counter in this acquisition path, so guaranteed overlap
remains zero and sample loss is not directly observable.
