# Where held improvements occur

The fitted-c constant-band profile's net held likelihood gain is concentrated
in the final excluded block. It is not evidence of broad improvement across
the scan. The age-dependent prior's fitted-c effect is very small.

| Paired comparison | Better held NLL blocks /7 | Total held NLL change | Assigned change /1909 |
|---|---:|---:|---:|
| Band constants, fitted-c | 4 | −85.236 | +10 |
| Age-aware timing, fitted-c | 4 | −1.384 | +3 |
| Band constants, c=0 sensitivity | 6 | −394.512 | +95 |
| Age-aware timing, c=0 sensitivity | 4 | −76.325 | +4 |

Negative NLL change is better. Each comparison uses its own matched baseline:
band profiling keeps the original blocked physical state fixed; timing-prior
continuations optimize over the broader matched research regional disk.
They must not be ranked as changes from one common baseline. The production
25km extra local disk was not enforced by common.refit; the timing experiment's
pre-score [domain erratum](../../2026_10_17_dsx01_iteration5/age_timing/blocked_domain_erratum.json)
retains exact endpoint feasibility flags.

![Paired changes across the seven excluded blocks](paired-blocks.png)

For fitted-c band profiling, 260–280s alone contributes−105.531 NLL and17 net
assignments. The other six blocks jointly regress+20.296 NLL and lose7 net
assignments. At220–240s the change is+30.370 NLL and−12 assignments. Requested
held coverage remains66/80. This motivates joint calibration tests, not
promotion of a constant-profile postprocessing step.

The80 requested held observations occupy only TWO excluded time blocks,
20–40s and180–200s, although they span three named windows. Seven whole-scan
blocks and one station are still a small, dependent evaluation. No p-values,
independent-sample claims, satellite identity truth or new-position claim.

`report.py` reads saved predictions without fitting, reconstructs public125Hz
conditional densities and exactly replays every age-policy saved assignment,
both methods' aggregate counts and held NLL. Original timestamps are checked.
The age prediction exports omit timestamps; their corresponding saved score
exports supply source-ordered metadata, with exact held-mask and label replay.
All inputs are hash-bound in `summary.json`. The two c arms are conditional
after fitted-c production discovery, not separate whole-pipeline c=0 discovery.

Two component tests verify paired block sums, lost-support debit and rejection
of misaligned/nonboolean input. This is a diagnostic on already selected
training-only results: no new inference, RF, position read or model selection.
