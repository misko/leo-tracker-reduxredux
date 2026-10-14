# C001 held observations reverse the training preference

The lower-anchor C solution predicts held observations better than the original full-band solution in both bands, although both training-band likelihoods preferred the original solution. This supports a generalization problem among these fitted states. It does not establish which modeling mechanism caused it or authorize selecting a new winner using these observations.

| Frozen stationary state | Training NLL | Held CH1–8 NLL/window | Held CH1–4 NLL/window | Held CH5–8 NLL/window |
|---|---:|---:|---:|---:|
| Original full | 41529.962579 | 13.771388 | 12.963739 | 14.989152 |
| Lower anchor release | 41779.457003 | 13.555253 | 12.761949 | 14.751387 |
| Upper anchor release | 43404.248856 | 14.593752 | 14.228376 | 15.144662 |

Lower NLL is better. All states use the same original partition: 3,229 training windows and 805 disjoint held windows (484 lower and 321 upper). Position, satellite timing, fitted c, receiver calibration and candidate bank were frozen before held projection. Predictions use the original native objective and exact branch timestamps. Each band's NLL sums to the full NLL within 1e-7. These are restrictions of full-band fitted states, not independent half-band fits.

The upper-anchor state, which was nearest the configured reference, remains worst on held likelihood. Thus held likelihood is not established as a reliable position selector either. DS22's reference remains configured and unconfirmed. No reference was read by this diagnostic, no held-based selection occurred, and the original training winner remains unchanged.

Source: `91a02b3a3`, `tools/ds22_c_anchor_held.py`; four tests and Ruff passed. The actual diagnostic completed in 42.823 seconds with nine held predictions and zero optimizer calls. Receipts: `local/ds22-c-anchor-held-v1/DS22-001`; report SHA256 `ab735cff26bbbe58a973a10f263f588e7eee77bb4a0705096559e48a3e3e63c6`.
