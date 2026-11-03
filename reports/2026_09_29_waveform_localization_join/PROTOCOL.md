# Join independent waveform diagnostics to localization evidence

Observational audit, frozen before execution. Join all 4,328 bank-eligible tracks
from nine target eight-scan panels to the existing DS7–DS9 all-track symbol census
by exact session and track ID. Verify observation hashes, manifest identity and
decoder binding. Report missing census support separately (including sub-5-MS/s
recordings) rather than interpreting absence as failed waveform quality.

Use the original decoder's fixed qualified/insufficient-pilots labels. Join the
selected excerpt visit to the frozen localization training mask. The excerpt was
selected by maximum pilot margin across all track visits; even selected training
visits were chosen using a whole-track ranking. Thus these labels cannot be used
as leakage-free localization priors without re-extraction under a training-only
selection rule. Do not fit, gate, reweight or select geographic models here.

Report dataset counts, training/held selection, conditional signal responsibility
and strong-candidate residual held median error by waveform status. Residual
summaries only cover the prior 3,983 eligible conditional cases and must retain
their denominator separately. Strong means responsibility times maximum candidate
weight >=0.5. No sequence state is treated as a satellite identity. No new IQ
read, RF, production mutation or geographic fit.
