# Fixed-position cross-band drift allocation comparison

Use the frozen eight-scan cross-band drift screen and its unchanged remaining-24
confirmation as prerequisites. Reconstruct each target pair's training-only
offset prediction. Its proposed differential correction is the fitted line
minus that pair's own constant training prediction, applied only within the
donor-center time interval. Convert native Hz to canonical11.2GHz Hz.

Exclude every pair touching a track occurring in multiple eligible pair rows;
leave those tracks unchanged. Apply corrections to all observations of the
remaining paired tracks using time alone. Preserve all unpaired tracks and
all observations, timestamps, masks and causal candidate banks.

If d is the predicted RX1-minus-RX0 drift, apply RX1 -= alpha*d and
RX0 += (1-alpha)*d, for alpha=0,0.5,1. These represent RX1 unchanged,
symmetric, and RX0 unchanged. Retain all three assumptions and the unchanged
baseline. Common receiver drift remains unidentifiable.

At each original qualified IID training endpoint, profile candidate CFOs with
the unchanged Student-t4/100Hz likelihood and candidate mixture. Report training
score, conditional held score (joint mixture normalizer minus training mixture
normalizer), MAP changes and coverage. Replay original training scores within
1e-6 nats. Never use geographic errors to choose corrections or allocations.

For any further geographic experiment require at least one allocation with
positive total and median held gain and at least5/8 scan wins. This gate is
only a necessary advancement check; passing is not position validation and
does not select a receiver allocation as truth. If none passes, stop this
correction policy before position fitting. One thread,90second cap, no new IQ,
orbit update or position optimization. Retain failures without replacement.
