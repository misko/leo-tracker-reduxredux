# Synthetic phase-assisted association qualification protocol

This observation-level simulation qualifies a candidate scorer, not waveform
extraction or real-sky association. Freeze protocol and source before generating
or evaluating held trajectories. Seed 20260930 creates 36 independent whole
trajectory units and assigns 18/18 to random outer train/held sets. Labels and
Doppler-close decoys are generated from latent trajectory state before noise or
scores. No chronological split or held tuning is allowed.

Each unit contains two sources, two receivers, 25 observations over four seconds,
and five candidate source-pair trajectories. Doppler follows range rate and RF.
Per-receiver/source phase is generated first from source direction, RF, a
counterfactual 8 cm baseline at 79 degrees clockwise from north, shared receiver
drift, channel mismatch, and noise. The source/receiver double difference is
then derived; it is never simulated directly. Candidate phase uses the same
geometric equation. The baseline is a sensitivity fixture, not hardware truth.

Every trajectory randomly assigns complete observation times to local calibration
or response. Candidate-independent Doppler offsets and one phase intercept are
fit on calibration only. Outer training labels estimate global Doppler/phase
scales and whether response-phase concentration supports use. Those fixed values
score every held candidate. Report true-candidate rank and log loss for Doppler
alone, Doppler plus phase, and a 90-degree baseline-orientation control.

Run calibrated, frequency/source-dependent mismatch, and independent-phase
regimes. The phase scorer abstains for a regime when training true-model residual
resultant is below 0.8 or RMS exceeds 0.8 rad. This prespecified authority gate
must also suppress phase coverage under independent phase. Mismatch outcomes are
retained even if phase harms scoring. Success is improved held rank/log loss in
the calibrated regime without spurious coverage in the independent regime; it
does not establish real-data improvement, geometry calibration, or identity.
