# Earlier-orbit health is available before inference, but the required orbit is not

An exact causal census recovered the earlier-orbit failure on DS30-0160 after **2.052 CPU s of named preparation**. The three-sample health check itself took **20.63 ms** over the 1,400 rows in each of the ordinary and genuine previous catalogues. Both catalogues found NORAD 58706 unusable. The genuine earlier catalogue digest, collected snapshot, epoch and original origin matched the failure captured by the actual historical retry. The ordinary saved DS30-0316 control had no earlier-row fault at those samples. [Frozen protocol](early-causal-history-protocol.md) · [Sealed receipt](measurements/early-causal-history.json.gz)

| Saved input | Named preparation CPU, s | CPU for both prior checks, ms | Current rows | Unusable rows per checked catalogue | Prepare-only process elapsed, s |
|---|---:|---:|---:|---:|---:|
| DS30-0160, archived history support | 2.052 | 20.63 | 1,400 | 1 | 3.445 |
| DS30-0316, archived ordinary complete control | 2.707 | 19.48 | 1,472 | 0 | 4.174 |

Both processes stopped at the original inference boundary. They used the original signed full-aperture packets, cutoff, archives and offers already staged in tmpfs and made zero input-block reads. No terminal, figures or new position estimate were produced. Six focused component tests passed. [Census and bindings](early_causal_history.py) · [Harness](early_causal_history_trial.py) · [Tests](../../../tests/pipeline_eval/test_early_causal_history.py)

## Why the census cannot choose the recovery route

The census reports which earlier elements are unavailable at three exact alignment samples. The named solver chooses the relevant rows from its cold winner. It can withhold on an empty retained mask before asking for a previous bank. The cumulative route can withhold on its exterior proof or complete its own proposal before invoking named inference. These decisions use track assignment, region and fit outputs absent from the census. The exact previous-bank assertion depends on the nominated row set as well as the archived orbital elements.

The synthetic prior held one usable earlier orbit, one earlier orbit with a failed propagation and one current orbit with no earlier element at all. The unchanged `previous_bank` succeeded when the selected set used the healthy row, preserved its ordinary unavailable-history behavior for the absent row, and raised only when the selected set used the failed row. Dispatching on the existence of that failed row would therefore send the first two valid calls to an unnecessary recovery. A clean three-sample census rules out this particular three-sample failure for checked rows. The downstream kernel has a separate full-grid propagation check.

The cheapest demonstrated exact in-fit checkpoint is when the actual selected bank reaches the three-sample assertion. It already precedes extended earlier-orbit interpolation in that call. The named-only adapter recovers there and retains the full preparation and selected cold winner. The measured named-only recovery took 11.120 s elapsed on the same input and reproduced both calibration arms, every ordered owner row and all eight PNGs. A cumulative dispatcher still needs its ordinary route outcome before it can authorize a handoff. Its verified 20.428 s elapsed includes the failed prefix and the independent named preparation. The original named retry took 15.999 s elapsed. No earlier positive certificate or cross-route prepared-state equivalence was established, so the study stopped before launching a new dispatch candidate. [Exact named-only recovery](named-history-once.md) · [Measured cumulative dispatch](cumulative-history-dispatch.md)

The result and launch binding expand to SHA-256 `1f69aeebd9826a2af6b7beee9bfd414c65fd5f89c6441a0e1f2a4e391dcc372b` and `50658485f3ecffb63dda6371b64fcd23e40a519593c2c25dcad5d238bbed0492`. [Launch binding](measurements/early-causal-history-binding.json.gz)
