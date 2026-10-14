# Both bands prefer the farther C001 solution at the tested states

An exact row restriction of the original full C likelihood shows that both bands prefer the original full-band solution over either converged alternative. The candidate bank, full-frame calibration, fitted c, satellite timing, mixture priors and nuisance values were retained separately for each saved stationary state. This is a likelihood decomposition, not a refit of either half-band model.

| Stationary state | CH1–4 NLL | CH5–8 NLL | CH1–4 signal mass | CH5–8 signal mass | Parameter prior penalty |
|---|---:|---:|---:|---:|---:|
| Original full | 22896.833093 | 18633.129486 | 1155.878512 | 799.815474 | 333.588480 |
| Lower anchor release | 23008.618538 | 18770.838465 | 1120.135424 | 757.318632 | 253.139041 |
| Upper anchor release | 23878.729583 | 19525.519273 | 971.708878 | 639.245299 | 214.625677 |

Each state has 1,811 lower-band and 1,418 upper-band training windows. Signal mass is the sum of posterior signal probabilities, not a count of independently verified detections. The original full solution attributes more mass to satellites and less to clutter in both bands. Its parameter prior penalty is worse, so that prior is not causing its preference over these alternatives.

Any strictly positive weighting of the two likelihood contributions still prefers the original state among these three fixed states. This does not rule out different optima after reweighting/refitting, and does not apply to arbitrary changes in overall prior strength. It does rule out a simple explanation in which one band's likelihood is pulling against the other's preference at these endpoints.

The configured-reference distances were reported separately in `DS22_C_CHECKPOINT_RESULTS.md` (21.266493, 9.481242 and 3.404501 km respectively); DS22 reference remains unconfirmed. No reference or held data were read by this diagnostic. The next hypothesis to examine is whether the added signal mass corresponds to temporally consistent satellite assignments or isolated chance matches under the singleton likelihood. This result alone does not establish that mechanism.

The saved original objectives and NLLs replayed, and the two band NLLs reproduced the full NLL within 1e-7 for every state. Frozen source `f7d2cad9e`; two tests and Ruff pass. Three original objective evaluations, three additional orbit predictions, six restricted likelihood evaluations, zero optimizer calls. Receipts: `local/ds22-c-checkpoint-band-scores-v1/DS22-001`.
