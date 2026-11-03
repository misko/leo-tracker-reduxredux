# DS10-D08 coherent-v1 root-cause diagnostic

Truth-free replay of frozen inputs and sealed fits. No fit was performed and evaluation coordinates were not loaded.

## Conclusion

- Primary cause: shared receiver-line conflict across captures.
- Secondary mechanism: the 8-candidate proxy likelihood has a far-position basin that wins model selection; 16- and 24-candidate fits remain near rough.
- Wholesale candidate switching is not primary: pair-vs-single catalog agreement is 95.8% overall and 96.8% for ladder-qualifying tracks.

## Receiver-line conflict

- RX0: child intercept gap 85248.2 Hz over 423.930 s requires 201.09 Hz/s (4.02x the +/-50 Hz/s bound); joint initialization is 50.00 Hz/s.
- RX1: child intercept gap 85811.2 Hz over 423.930 s requires 202.42 Hz/s (4.05x the +/-50 Hz/s bound); joint initialization is 50.00 Hz/s.

## Candidate banks

- 8 candidates: position [-163.06721804135438, -174.86663993349345], distance from rough 124.44 km, objective 101098.04 to 100847.35, selection score 100883.34, success=True, tau-at-bound=1.
- 16 candidates: position [-81.84560133067697, -81.18810943066087], distance from rough 0.62 km, objective 103413.44 to 103218.53, selection score 103290.50, success=True, tau-at-bound=0.
- 24 candidates: position [-84.09914341545607, -80.90602315921225], distance from rough 2.25 km, objective 107406.85 to 107171.23, selection score 107279.18, success=False, tau-at-bound=0.

## Interpretation

- The 8-candidate winner contains leading candidates from both captures, but moves far from the joint rough solution.
- The 16- and 24-candidate alternatives stay near rough, so the catastrophe is not inherited from rough localization.
- Saturated shared-line initialization and the child offset gap create a misspecified nuisance model; bank truncation then exposes a lower proxy-objective far basin.
- This conditional likelihood is not blind validation and no reference truth was used for diagnosis or selection.

Numerical replay elapsed: 0.942 s.
JSON detail: root-cause-diagnostic.json.
