# Pre-geographic channel attribution diagnostic

The parent coordinator requested separate CH8-only and CH7-only ordinary VI
interventions after the complete seven-owner RF panel. Freeze both complete
channel subsets before geographic evaluation. CH8-only changes every nominated
CH8 native point and leaves every CH7 control and other observation original;
CH7-only does the converse. Do not choose individual points or subsets using
geographic results. All 187 CH8 and 193 CH7 points remain in their original
likelihoods; this is a delta-vector partition, not observation removal.

Reuse each case/c-arm's original ordinary VI result from the main matched run.
Add eight cold matched fits: two channel vectors by two scans by two c arms.
Use the same zero position/phase initialization, five 48-iteration refresh
rounds, original assignments, priors, region, gates and Gamma updates. Bound
each case worker to 70 seconds and the external job to 90 seconds. The fitted-c
and c=0 arms use identical native delta vectors. Preserve all failed results.
These are fixed-assignment attribution diagnostics, not independent validation
or a global regional search. Geographic evaluation follows both inference seals.
