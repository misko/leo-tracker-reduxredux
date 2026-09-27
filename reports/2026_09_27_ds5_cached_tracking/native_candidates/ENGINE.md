# Native candidate-budget extension

This research extension builds the frozen TG11 engine with one or two blind
hypotheses per 20 ms probe. It does not change the TG11 ABI, screen, guided
measurement, templates, interference conditioning, CFO searches, timing
lattice, fractional fit, or final full-aperture exact/control GLRT.

The deployed `leo_presence_result` already has two candidate slots. With
`LEO_PRESENCE_CANDIDATES=2`, the existing coarse search makes a second peak
selection pass. It suppresses a second proposal when it is within five
circular epoch samples and 10 kHz of the first proposal. Each retained proposal
then follows the complete existing confirmation path. `POWER_PROPOSAL=1`
preserves selection order rather than sorting by final score.

The public research interface is:

```python
engine = NativeCandidates(rate, edge, candidate_budget=1_or_2)
screen = engine.screen(raw, receiver=rx)
observations = engine.blind(raw, receiver=rx, screen=screen)
guided = engine.guided(raw, receiver=rx, probe_index=probe,
                       predicted_local_epoch_sample=epoch,
                       scoring_cfo_hz=scoring_cfo,
                       expected_physical_cfo_hz=physical_cfo)
```

The context manager, `close`, arguments, and result dataclasses are identical
to `NativeTG11`, so the current causal controller can consume either budget.
Each binary and its complete source inventory have a separate build receipt.

Four hypotheses are deferred. Supporting four requires a new result ABI,
wider retained/support/region arrays, generalized suppression against every
retained hypothesis, Python bounds changes, and controller/reporting review.
That is a separate scientific and ABI change rather than a profile override.

No saved IQ is evaluated here. The component checks use deterministic
constructed arrays only. A later protocol must measure quality and complete
caller cost; candidate two repeats the fine CFO and fractional GLRT work, so
its cost is data-dependent and cannot be inferred from this build.
